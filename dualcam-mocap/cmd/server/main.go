package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"sync"
	"time"

	"github.com/dmparrow/puppetry/dualcam-mocap/internal/rpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type blenderHub struct {
	mu      sync.Mutex
	clients map[net.Conn]struct{}
}

func newBlenderHub() *blenderHub { return &blenderHub{clients: map[net.Conn]struct{}{}} }

func (h *blenderHub) serve(addr string) error {
	ln, err := net.Listen("tcp", addr)
	if err != nil { return err }
	log.Printf("Blender bridge listening on %s", addr)
	for {
		conn, err := ln.Accept()
		if err != nil { return err }
		h.mu.Lock(); h.clients[conn] = struct{}{}; h.mu.Unlock()
		log.Printf("Blender connected: %s", conn.RemoteAddr())
		go func(c net.Conn) {
			defer func() { h.mu.Lock(); delete(h.clients, c); h.mu.Unlock(); c.Close() }()
			_, _ = io.Copy(io.Discard, bufio.NewReader(c))
		}(conn)
	}
}

func (h *blenderHub) broadcast(sk *rpc.Skeleton) {
	points := map[string]map[string]any{}
	for _, j := range sk.Joints {
		points[j.Name] = map[string]any{"xyz": []float32{j.X, j.Y, j.Z}, "confidence": j.Confidence}
	}
	payload := map[string]any{
		"type": "skeleton", "seq": sk.Sequence, "ts_ns": sk.TimestampNS,
		"capture_mode": sk.CaptureMode, "root_translation": sk.RootTranslation,
		"processing_ms": sk.ProcessingMS, "points": points,
	}
	line, _ := json.Marshal(payload); line = append(line, '\n')
	h.mu.Lock(); defer h.mu.Unlock()
	for c := range h.clients {
		_ = c.SetWriteDeadline(time.Now().Add(50 * time.Millisecond))
		if _, err := c.Write(line); err != nil { c.Close(); delete(h.clients, c) }
	}
}

type mocapServer struct {
	worker *grpc.ClientConn
	hub    *blenderHub
}

func (s *mocapServer) StreamFrames(stream grpc.ServerStream) error {
	latest := make(chan *rpc.FrameSet, 1)
	recvErr := make(chan error, 1)
	go func() {
		for {
			fs, err := rpc.RecvFrameSet(stream)
			if err != nil { recvErr <- err; return }
			select {
			case latest <- fs:
			default:
				select { case <-latest: default: }
				latest <- fs
			}
		}
	}()

	for {
		select {
		case err := <-recvErr:
			if err == io.EOF { return nil }
			return err
		case fs := <-latest:
			ctx, cancel := context.WithTimeout(stream.Context(), 2*time.Second)
			sk, err := rpc.InvokeInference(ctx, s.worker, fs)
			cancel()
			if err != nil { log.Printf("inference seq=%d failed: %v", fs.Sequence, err); continue }
			s.hub.broadcast(sk)
			if err := rpc.SendSkeleton(stream, sk); err != nil { return err }
		}
	}
}

func main() {
	grpcAddr := flag.String("grpc", ":50051", "camera gRPC listen address")
	workerAddr := flag.String("worker", "127.0.0.1:50052", "Python inference worker")
	blenderAddr := flag.String("blender", ":8766", "Blender TCP JSON bridge")
	flag.Parse()

	opts := append([]grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}, rpc.DialOptions()...)
	worker, err := grpc.NewClient(*workerAddr, opts...)
	if err != nil { log.Fatal(err) }
	defer worker.Close()

	hub := newBlenderHub()
	go func() { if err := hub.serve(*blenderAddr); err != nil { log.Fatalf("Blender bridge: %v", err) } }()

	ln, err := net.Listen("tcp", *grpcAddr)
	if err != nil { log.Fatal(err) }
	server := grpc.NewServer(grpc.ForceServerCodec(rpc.JSONCodec{}))
	rpc.RegisterMocapServer(server, &mocapServer{worker: worker, hub: hub})
	log.Printf("mocap gRPC listening on %s; inference=%s", *grpcAddr, *workerAddr)
	if err := server.Serve(ln); err != nil { log.Fatal(fmt.Errorf("grpc serve: %w", err)) }
}
