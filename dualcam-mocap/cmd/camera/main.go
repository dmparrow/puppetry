package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"sync/atomic"
	"time"

	"github.com/blackjack/webcam"
	"github.com/dmparrow/puppetry/dualcam-mocap/internal/rpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type camera struct {
	id  uint32
	dev *webcam.Webcam
}

func openCamera(id uint32, path string, width, height uint, fps float64) (*camera, error) {
	dev, err := webcam.Open(path)
	if err != nil { return nil, err }
	formats := dev.GetSupportedFormats()
	var mjpeg webcam.PixelFormat
	for f, name := range formats {
		n := strings.ToLower(name)
		if strings.Contains(n, "mjpeg") || strings.Contains(n, "motion-jpeg") || strings.Contains(n, "motion jpeg") {
			mjpeg = f
			break
		}
	}
	if mjpeg == 0 {
		dev.Close()
		return nil, fmt.Errorf("%s does not expose MJPEG; supported formats: %v", path, formats)
	}
	_, gotW, gotH, err := dev.SetImageFormat(mjpeg, uint32(width), uint32(height))
	if err != nil { dev.Close(); return nil, err }
	if err := dev.SetFramerate(float32(fps)); err != nil { log.Printf("%s: requested fps %.1f: %v", path, fps, err) }
	if err := dev.SetBufferCount(3); err != nil { log.Printf("%s: buffer count: %v", path, err) }
	if err := dev.StartStreaming(); err != nil { dev.Close(); return nil, err }
	log.Printf("camera %d %s streaming %dx%d MJPEG", id, path, gotW, gotH)
	return &camera{id: id, dev: dev}, nil
}

func (c *camera) close() { _ = c.dev.StopStreaming(); _ = c.dev.Close() }

func (c *camera) frame() (rpc.CameraFrame, error) {
	if err := c.dev.WaitForFrame(2); err != nil { return rpc.CameraFrame{}, err }
	data, err := c.dev.ReadFrame()
	if err != nil { return rpc.CameraFrame{}, err }
	if len(data) == 0 { return rpc.CameraFrame{}, fmt.Errorf("empty frame") }
	copyBytes := append([]byte(nil), data...)
	return rpc.CameraFrame{CameraID: c.id, TimestampNS: time.Now().UnixNano(), JPEG: copyBytes}, nil
}

func main() {
	server := flag.String("server", "127.0.0.1:50051", "Go mocap server host:port")
	mode := flag.String("mode", "mono", "mono or stereo")
	camA := flag.String("cam-a", "/dev/video0", "camera A V4L2 device")
	camB := flag.String("cam-b", "/dev/video2", "camera B V4L2 device")
	width := flag.Uint("width", 1280, "capture width")
	height := flag.Uint("height", 720, "capture height")
	fps := flag.Float64("fps", 30, "capture fps")
	flag.Parse()
	if *mode != "mono" && *mode != "stereo" { log.Fatal("--mode must be mono or stereo") }

	a, err := openCamera(0, *camA, *width, *height, *fps)
	if err != nil { log.Fatal(err) }
	defer a.close()
	var b *camera
	if *mode == "stereo" {
		b, err = openCamera(1, *camB, *width, *height, *fps)
		if err != nil { log.Fatal(err) }
		defer b.close()
	}

	opts := append([]grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}, rpc.DialOptions()...)
	conn, err := grpc.NewClient(*server, opts...)
	if err != nil { log.Fatal(err) }
	defer conn.Close()
	stream, err := rpc.NewMocapStream(context.Background(), conn)
	if err != nil { log.Fatal(err) }
	defer rpc.CloseSend(stream)

	var received atomic.Uint64
	go func() {
		for {
			var sk rpc.Skeleton
			if err := rpc.RecvSkeleton(stream, &sk); err != nil { log.Printf("skeleton stream ended: %v", err); return }
			received.Add(1)
			if sk.Sequence%60 == 0 { log.Printf("skeleton seq=%d joints=%d inference=%.1fms", sk.Sequence, len(sk.Joints), sk.ProcessingMS) }
		}
	}()

	host, _ := os.Hostname()
	log.Printf("streaming %s capture from %s to %s", *mode, host, *server)
	var seq uint64
	for {
		fa, err := a.frame()
		if err != nil { log.Printf("camera A: %v", err); continue }
		frames := []rpc.CameraFrame{fa}
		if b != nil {
			fb, err := b.frame()
			if err != nil { log.Printf("camera B: %v", err); continue }
			frames = append(frames, fb)
		}
		fs := &rpc.FrameSet{Sequence: seq, CaptureMode: *mode, Frames: frames}
		if err := rpc.SendFrameSet(stream, fs); err != nil { log.Fatalf("send: %v", err) }
		seq++
	}
}
