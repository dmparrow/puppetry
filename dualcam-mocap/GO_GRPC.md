# Go + gRPC mocap branch

This branch moves capture and service orchestration out of Python.

```text
Linux camera machine
  mocap-camera (Go, direct V4L2/MJPEG)
      |
      | bidirectional gRPC :50051
      v
GPU machine
  mocap-server (Go)
      | latest-frame-only queue
      | gRPC unary inference
      v
  inference (Python, temporary, CUDA) :50052
      | RTMW3D mono / RTMPose stereo
      v
  mocap-server
      |
      +--> skeleton response over gRPC to camera client
      +--> newline JSON TCP :8766 to Blender
```

## Why the Python worker remains

The current model adapters already work with `rtmlib` and `skellytracker`. They are isolated behind the `mocap.v1.Inference/Infer` contract. A future C++/ONNX Runtime or TensorRT worker can replace the Python service without changing the camera client, Go server, Blender add-on, or public ports.

## gRPC contract

`proto/mocap.proto` is the canonical schema. The first vertical slice uses gRPC with a JSON codec so both Go and the temporary Python worker can share the contract without checked-in generated protobuf bindings. JPEG byte fields are base64 encoded by the JSON codec.

Once the service shape is proven on hardware, generate normal protobuf bindings and switch the codec to protobuf binary. That is a wire-format change only; the RPC and message semantics stay the same.

## GPU machine

```bash
chmod +x run_go_stack.sh
./run_go_stack.sh
```

This starts:

- `mocap-server`: Go orchestration/broker, no GPU access
- `inference`: Python CUDA worker, the only GPU-enabled container

Ports exposed to the LAN:

- `50051/tcp` - camera gRPC
- `8766/tcp` - Blender skeleton bridge

`50052` is internal to the Compose network.

## Camera machine

Linux/V4L2 only for this first Go capture backend.

```bash
chmod +x install_go_camera.sh
./install_go_camera.sh
```

Mono:

```bash
./bin/mocap-camera --server GPU_IP:50051 --cam-a /dev/video0
```

Stereo:

```bash
./bin/mocap-camera \
  --server GPU_IP:50051 \
  --mode stereo \
  --cam-a /dev/video0 \
  --cam-b /dev/video2
```

The camera backend requests MJPEG directly from V4L2. Frames are copied from the driver buffer and placed directly into gRPC; there is no OpenCV dependency and no JPEG decode/re-encode on the camera machine.

## Blender

No change. The existing add-on connects to the GPU machine on TCP `8766` and receives the same skeleton JSON payload as the Python-server branch.

## Next worker

Target interface for the future native worker:

```text
mocap.v1.Inference/Infer(FrameSet) -> Skeleton
```

Candidate implementation:

```text
C++
  ONNX Runtime CUDA / TensorRT
  RTMPose preprocessing
  mono 3D or stereo 2D inference
  triangulation
  filtering
```

Only the Compose `inference` service needs to change.
