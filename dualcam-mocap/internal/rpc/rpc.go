package rpc

import (
	"context"
	"encoding/json"
	"io"

	"google.golang.org/grpc"
	"google.golang.org/grpc/encoding"
)

const (
	MocapStreamMethod = "/mocap.v1.Mocap/StreamFrames"
	InferenceMethod   = "/mocap.v1.Inference/Infer"
)

type CameraFrame struct {
	CameraID    uint32 `json:"camera_id"`
	TimestampNS int64  `json:"timestamp_ns"`
	JPEG        []byte `json:"jpeg"`
}

type FrameSet struct {
	Sequence    uint64        `json:"sequence"`
	CaptureMode string        `json:"capture_mode"`
	Frames      []CameraFrame `json:"frames"`
}

type Joint struct {
	Name       string  `json:"name"`
	X          float32 `json:"x"`
	Y          float32 `json:"y"`
	Z          float32 `json:"z"`
	Confidence float32 `json:"confidence"`
}

type Skeleton struct {
	Sequence        uint64  `json:"sequence"`
	TimestampNS     int64   `json:"timestamp_ns"`
	CaptureMode     string  `json:"capture_mode"`
	RootTranslation string  `json:"root_translation"`
	Joints          []Joint `json:"joints"`
	ProcessingMS    float32 `json:"processing_ms"`
}

type JSONCodec struct{}

func (JSONCodec) Name() string { return "json" }
func (JSONCodec) Marshal(v any) ([]byte, error) { return json.Marshal(v) }
func (JSONCodec) Unmarshal(data []byte, v any) error { return json.Unmarshal(data, v) }

func init() { encoding.RegisterCodec(JSONCodec{}) }

func DialOptions() []grpc.DialOption {
	return []grpc.DialOption{grpc.WithDefaultCallOptions(grpc.ForceCodec(JSONCodec{}))}
}

type MocapServer interface {
	StreamFrames(grpc.ServerStream) error
}

func RegisterMocapServer(s *grpc.Server, impl MocapServer) {
	s.RegisterService(&grpc.ServiceDesc{
		ServiceName: "mocap.v1.Mocap",
		HandlerType: (*MocapServer)(nil),
		Streams: []grpc.StreamDesc{{
			StreamName:    "StreamFrames",
			Handler:       func(_ any, stream grpc.ServerStream) error { return impl.StreamFrames(stream) },
			ServerStreams: true,
			ClientStreams: true,
		}},
	}, impl)
}

func NewMocapStream(ctx context.Context, cc *grpc.ClientConn) (grpc.ClientStream, error) {
	return cc.NewStream(ctx, &grpc.StreamDesc{ServerStreams: true, ClientStreams: true}, MocapStreamMethod, grpc.ForceCodec(JSONCodec{}))
}

func SendFrameSet(stream grpc.ClientStream, fs *FrameSet) error { return stream.SendMsg(fs) }
func RecvSkeleton(stream grpc.ClientStream, out *Skeleton) error { return stream.RecvMsg(out) }
func CloseSend(stream grpc.ClientStream) error { return stream.CloseSend() }

func InvokeInference(ctx context.Context, cc *grpc.ClientConn, fs *FrameSet) (*Skeleton, error) {
	out := new(Skeleton)
	if err := cc.Invoke(ctx, InferenceMethod, fs, out, grpc.ForceCodec(JSONCodec{})); err != nil { return nil, err }
	return out, nil
}

func RecvFrameSet(stream grpc.ServerStream) (*FrameSet, error) {
	fs := new(FrameSet)
	if err := stream.RecvMsg(fs); err != nil { return nil, err }
	return fs, nil
}

func SendSkeleton(stream grpc.ServerStream, sk *Skeleton) error { return stream.SendMsg(sk) }

func IsEOF(err error) bool { return err == io.EOF }
