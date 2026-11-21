# Hailo toolchain for issue #406 (plant / not-plant segmentation)

Written 2026-11-20 on the x86 training host (Ubuntu 26.04.1, Python 3.13.2, RTX 2060 SUPER 8 GB,
driver 595.91.07, Docker 29.8.0, 30 GB RAM, Ryzen 7 5700X with AVX2). No rig was contacted.

Files made for this note:

| Path | What |
|---|---|
| `hailo/docker/hailo8/Dockerfile` | Hailo-8 compile image: DFC 3.33.1 + Model Zoo v2.18 |
| `hailo/docker/hailo10h/Dockerfile` | Hailo-10H compile image: DFC 5.1.0 + Model Zoo v5.1.0 |
| `hailo/docker/hailo.sh` | `check`, `build-base`, `build`, `run`, `gpu-test` |
| `hailo/downloads/hailo8/`, `hailo/downloads/hailo10h/` | Empty. Aaron puts the Hailo wheels here |
| `hailo/prebuilt/<chip>/` | Hailo's own compiled zoo HEFs for 4 segmentation models, for a first speed test on each rig |
| `src/hailo_model_zoo-hailo8/` | Model Zoo clone, tag v2.18 (commit dc402c7) |
| `src/hailo_model_zoo-hailo10h/` | Model Zoo clone, tag v5.1.0 (commit c13e20e) |

---

## 1. Versions per chip

| | Production `ac-testing` | Development `npec-rig-01` |
|---|---|---|
| Chip | Hailo-8 | Hailo-10H |
| HailoRT on the rig | 4.23.0 | 5.1.1 |
| **Dataflow Compiler (DFC)** | **3.33.1** (fallback 3.33.0) | **5.1.0** |
| **Model Zoo tag** | **v2.18** (fallback v2.17 with DFC 3.33.0) | **v5.1.0** |
| `--hw-arch` | `hailo8` | `hailo10h` |
| Hailo software suite | Hailo-8/8L suite 2025-10 (DFC 3.33.0, HailoRT 4.23.0, Model Zoo 2.17) | Hailo-10H/15 suite 2025-10, probably (HailoRT 5.1.0 was released on GitHub 2025-09-30; not read from the gated release notes) |
| TensorFlow inside the DFC | 2.18 | 2.18 |
| Host OS (documented) | Ubuntu 22.04 or 24.04, x86_64 (WSL2 also listed) | Ubuntu 22.04 or 24.04, x86_64 |
| Python (documented) | 3.10, 3.11, 3.12 (3.12 from DFC 3.32; 3.8 dropped after DFC 3.31) | 3.10, 3.11, 3.12 (3.12 from DFC 5.1.0) |
| GPU stack for optimization | CUDA 12.5.1, cuDNN 9.10, driver 555 or newer (staff) / 525 (zoo docs) | CUDA 12.5.1, cuDNN 9.10 (zoo v5.1.0 docs). DFC 5.0.0 was CUDA 11.8 / cuDNN 8.9 |
| GPU architectures listed | Pascal, Turing, Ampere (RTX 2060 SUPER is Turing: listed) | same |

The two chips need two separate compilers. DFC 3.x compiles only for Hailo-8/8R/8L; DFC 5.x
only for Hailo-10H/15H/15M/15L/10P/12L. Model Zoo v2.16 and later removed Hailo-10H from the 2.x
line, and the 5.x README says Hailo-8 is supported on 2.x / DFC 3.x only.

### Why these versions (evidence)

The official "Release Versions Compatibility" table is in the AI Software Suite user guide behind
the Developer Zone login, so I could not read it. The pairing comes from public sources that agree:

1. **Hailo's own app framework** (`hailo-ai/hailo-apps`, `main`, `hailo_apps/config/config.yaml`):
   "H8/H8L: HailoRT 4.23.x -> v2.18.0, HailoRT 4.24.x -> v2.19.0" and "H10: HailoRT 5.1.x -> v5.1.0".
   Its valid HailoRT:TAPPAS pairs include `hailo10h: 5.1.1:5.1.0`.
2. **Model Zoo v2.18** (`setup.py`): `DFC_VERSION = "3.33.1"`; README badge HailoRT 4.23.0;
   CHANGELOG "Update to use Dataflow Compiler v3.33.1". (Its README badge and GETTING_STARTED still
   say DFC 3.33.0: an inconsistency inside the tag. setup.py only warns on a mismatch.)
3. **Model Zoo v2.17**: DFC 3.33.0 + HailoRT 4.23.0 (CHANGELOG and setup.py). v2.19.0 moved to
   DFC 3.34.0 + HailoRT 4.24.0, so it is too new for production.
4. **Model Zoo v5.1.0**: DFC 5.1.0 + HailoRT 5.1.0 (CHANGELOG, setup.py `CUR_DFC_VERSION = "5.1.0"`).
   There is no Model Zoo 5.1.1 tag and I found no mention of a DFC 5.1.1. HailoRT 5.1.1 (GitHub
   release 2025-11-09) is a runtime patch; on 2025-11-12 Hailo staff told a Hailo-10H user with a
   HEF/HailoRT mismatch to take models from Model Zoo "5.1.0, not 5.1.1 or main".
5. **Raspberry Pi apt (trixie)**: `hailo-all` 5.1.1 depends on `hailort` 4.23.0 and
   `python3-hailort` 4.23.0-1; `hailo-h10-all` 5.1.1 depends on `h10-hailort` 5.1.1 and
   `python3-h10-hailort` 5.1.1-1. These match the two rigs.
6. **Ultralytics** documents its Hailo export as validated on Hailo-8L with HailoRT 4.23 and DFC 3.33.

### HEF compatibility rule (from HailoRT source)

`hef.cpp` in HailoRT 4.23.0 and 5.1.1 accepts HEF header versions 0 to 3, and refuses a HEF that
uses features the runtime does not know ("Failed opening non-compatible HEF with the following
unsupported extensions"). So an older HEF usually loads on a newer runtime, but a HEF from a newer
DFC can fail on an older runtime. Known case: DFC 3.31 changed the HEF checksum to XXHASH3_64 and
older HailoRT could not open those files. Rule for us: compile with exactly the DFC listed above,
never a newer one. Hailo's prebuilt zoo HEFs have header version 2 (hailo8, v2.18.0) and 3
(hailo10h, v5.1.0).

---

## 2. What Aaron must download

Hailo Developer Zone, Software Downloads: <https://hailo.ai/developer-zone/software-downloads/>
(free account; I did not log in). Pick the product (Hailo-8 or Hailo-10H), software package
"Dataflow Compiler", OS Linux, architecture x86. Exact page labels could not be checked because the
page needs a login; the build script matches any file named `hailo_dataflow_compiler-<version>-*.whl`.

**Hailo-8** -> `/home/txoof/temp.nobackup/npec-406-nn/hailo/downloads/hailo8/`

| | Download | Expected file name |
|---|---|---|
| Required | Dataflow Compiler, Python package (whl), **3.33.1** | `hailo_dataflow_compiler-3.33.1-py3-none-linux_x86_64.whl` |
| If 3.33.1 is not offered | Dataflow Compiler 3.33.0 (the one in suite 2025-10) | `hailo_dataflow_compiler-3.33.0-py3-none-linux_x86_64.whl` |
| Recommended | Dataflow Compiler User Guide, PDF, same version | any name |
| Optional, not needed to compile | HailoRT Python package, 4.23.0, x86_64, Python 3.10 | `hailort-4.23.0-cp310-cp310-linux_x86_64.whl` |

**Hailo-10H** -> `/home/txoof/temp.nobackup/npec-406-nn/hailo/downloads/hailo10h/`

| | Download | Expected file name |
|---|---|---|
| Required | Dataflow Compiler for Hailo-10H, Python package (whl), **5.1.0** | `hailo_dataflow_compiler-5.1.0-py3-none-linux_x86_64.whl` |
| Recommended | Dataflow Compiler User Guide, PDF, 5.1.0 | any name |
| Optional, not needed to compile | HailoRT Python package, 5.1.1, x86_64, Python 3.10 | `hailort-5.1.1-cp310-cp310-linux_x86_64.whl` |

Not needed: the AI Software Suite Docker archives (several GB each; the Hailo-8 one is reported as
`hailo8_ai_sw_suite_2025-10.tar.gz`), TAPPAS, the x86 HailoRT .deb and PCIe driver. The suite's
`hailo_ai_sw_suite_docker_run.sh` also refuses to start on a host with no Hailo PCIe device.

The DFC is proprietary software under Hailo's Developer Zone licence terms. The User Guide PDF holds
the supported-layer table and the full model-script reference, which I could not read.

After the download:

```bash
cd /home/txoof/temp.nobackup/npec-406-nn
hailo/docker/hailo.sh check            # prints the sha256 of each wheel: add them to section 9
hailo/docker/hailo.sh build hailo8     # image npec406/hailo-hailo8:dfc-3.33.1
hailo/docker/hailo.sh build hailo10h   # image npec406/hailo-hailo10h:dfc-5.1.0
hailo/docker/hailo.sh run hailo8 hailomz --help
```

Fallback if only DFC 3.33.0 is available for Hailo-8:

```bash
git clone --depth 1 --branch v2.17 https://github.com/hailo-ai/hailo_model_zoo.git src/hailo_model_zoo-hailo8-v2.17
DFC_VERSION=3.33.0 MZ_DIR=$PWD/src/hailo_model_zoo-hailo8-v2.17 hailo/docker/hailo.sh build hailo8
```

---

## 3. Docker images

Both Dockerfiles are the same apart from the chip, DFC version and zoo clone:

- Base `nvidia/cuda:12.5.1-runtime-ubuntu22.04`, pinned by digest
  `sha256:a057e3228e6c1c4ee1b777ecb3540156f62ce19b5e9082167f44d98fd3c2f378` (3.77 GB unpacked).
- apt: Python 3.10 (Ubuntu 22.04 system Python), `libcudnn9-cuda-12=9.10.2.21-1`,
  `cuda-nvcc-12-5=12.5.82-1` (ptxas and libdevice for TensorFlow XLA; the zoo uses `jit_compile`),
  graphviz, tk, build tools. Python 3.10 is chosen over 3.11/3.12 because Model Zoo v2.18 pins
  `matplotlib==3.5.2` (prebuilt wheels only up to Python 3.10), `scikit-image==0.20.0` and
  `pillow<=9.3.0` (none for 3.12).
- Stage `base` needs no Hailo files. Stage `dfc` bind-mounts `hailo/downloads/<chip>/` (the wheel
  is not copied into a layer), installs the DFC wheel, the optional HailoRT wheel if present, then
  the zoo clone with `pip install --no-build-isolation -e` (its `setup.py` imports the installed
  DFC to check the version; under pip's build isolation it would not find it).
- `HMZ_DATA=/work/cache/hailomz-<chip>`: zoo downloads go to the work root's `cache/`.
- `hailo.sh run` mounts the work root at `/work`, runs as the host user (files stay owned by
  txoof), uses `--ipc=host`, and adds `--gpus all` only when Docker has the NVIDIA runtime or a CDI
  spec. `HAILO_GPU=0|1` forces it.

Test done: `hailo.sh build-base hailo8` (stage without wheels) built in about 4 minutes:
image `npec406/hailo-base:cuda12.5.1-cudnn9.10-py3.10`, 6.83 GB. Run as the host user it has
Python 3.10.12 in `/opt/hailo-venv` (pip 26.3), `libcudnn.so.9.10.2`, ptxas 12.5, libdevice,
graphviz 2.43, a writable `$HOME`, and sees the work root at `/work`. The Hailo-10H image reuses
the same cached base layers.
Docker keeps images in `/var/lib/docker` on the root disk (349 GB free), not in the work root's
`cache/`; moving that needs sudo and is not worth it.
Not done: the `dfc` stage (needs the wheels).

---

## 4. GPU in Docker

| Check | Result |
|---|---|
| Docker | 29.8.0 client and server, cgroup v2, systemd |
| Docker without sudo | yes, `txoof` is in group `docker` |
| `docker info` runtimes | `io.containerd.runc.v2`, `runc` only. No `nvidia` |
| `nvidia-ctk --version` | not installed (`nvidia-ctk`, `nvidia-container-runtime`, `nvidia-container-cli` all missing) |
| CDI specs | none (`/etc/cdi`, `/var/run/cdi` absent) |
| `docker run --rm --gpus all ubuntu:22.04 nvidia-smi` | fails: `failed to discover GPU vendor from CDI: no known GPU vendor found` |
| Host GPU | RTX 2060 SUPER, 8192 MiB, driver 595.91.07 (`nvidia-driver-595-open`) |
| Ubuntu 26.04 archive | has `libnvidia-container1` and `libnvidia-container-tools` 1.19.0, but no `nvidia-container-toolkit` |

Commands for Aaron (needs sudo). From NVIDIA's install guide, toolkit 1.20.2-1:

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg2
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.20.2-1
sudo apt-get install -y \
  nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
  nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
  libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
  libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}
sudo nvidia-ctk runtime configure --runtime=docker
# Restarting Docker stops every running container, including other agents' jobs. Check first:
docker ps
sudo systemctl restart docker
# Only if `--gpus all` still reports the CDI error above:
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
```

Then, without sudo: `hailo/docker/hailo.sh gpu-test` (nvidia-smi in the CUDA 12.5.1 image), and
after a build `hailo/docker/hailo.sh gpu-test hailo8` (TensorFlow lists the GPU inside the DFC image).
The driver (595, CUDA 13 era) runs CUDA 12.5 containers. Do not install the DFC on the host: Hailo
staff say CUDA 13 is not supported and the bundled TensorFlow cannot be rebuilt for it.

### Does optimization need the GPU?

It runs without one, but worse. With no GPU visible to TensorFlow the DFC prints
"Reducing optimization level to 0 (the accuracy won't be optimized and compression won't be used)
because there's no available GPU", and the log adds that level 0 "is not recommended for
production use" (DFC 3.33.0 reports, Nov 2025). Level 0 skips the fine-tuning (QFT) that the
default level 2 runs. Parsing and compiling (resource allocation) run on the CPU either way.
Practical meaning: we can compile CPU-only and measure the quantized mask against the float
model, but the GPU is needed to get the accuracy Hailo intends. 8 GB of VRAM is enough for
256x256 or 512x512 inputs; for 1024x1920 inputs lower the fine-tune batch size in the model script.
RAM: 30 GB on this host; an older third-party guide asks for 16 GB minimum, 32 GB recommended.

---

## 5. Model Zoo semantic segmentation catalog

Both tags hold the same six semantic segmentation networks. Figures are Hailo's, from
`docs/public_models/<CHIP>/<CHIP>_semantic_segmentation.rst`, measured by Hailo on its own host
(not a Pi 5). Contexts are from Hailo's profiler reports in `hailo/prebuilt/`.

| Model | Input (HxW) | Classes, dataset | Float / HW mIoU | Hailo-8 FPS (b1 / b8) | Hailo-10H FPS (b1 / b8) | Contexts H8 / H10H | Params, GOPs | Retraining Docker | Licence |
|---|---|---|---|---|---|---|---|---|---|
| unet_mobilenet_v2 | 256x256 | 3, Oxford-IIIT Pet | 77.3 / 77.2 | 662 / 662 | 693 / 693 | 1 / 1 | 10.08 M, 28.88 | no (TF2 tutorial source) | Apache-2.0 |
| deeplab_v3_mobilenet_v2_wo_dilation | 513x513 | 21, Pascal VOC | 71.5 / 71.2 (H10H 71.1) | 262 / 262 | 361 / 361 | 1 / 1 | 2.10 M, 3.21 | no | Apache-2.0 |
| deeplab_v3_mobilenet_v2 | 513x513 | 21, Pascal VOC | 76.0 / 74.6 | 121 / 121 | 90 / 90 | - | 2.10 M, 17.65 | no | MIT |
| stdc1 | 1024x1920 | 19, Cityscapes | 74.6 / 73.8 (H10H 73.7) | 57.6 / 58.0 | 20 / 33 | 1 / 2 | 8.27 M, 126.47 | yes, via `training/fcn` (Hailo mmsegmentation fork has `configs/stdc`) | Apache-2.0 |
| fcn8_resnet_v1_18 | 1024x1920 | 19, Cityscapes | 69.4 / 69.3 | 42.6 / 42.6 | 28 / 34 | 1 / 2 | 11.20 M, 142.82 | yes, `training/fcn` (official guide) | Apache-2.0 |
| segformer_b0_bn | 512x1024 | 19, Cityscapes | 69.8 / 67.8 (H10H 68.4) | 12.6 / 25.4 | 17 / 22 | - | 3.72 M, 35.76 | no | NVIDIA Source Code License (non-commercial) |

`training/fcn` builds from `nvcr.io/nvidia/pytorch:21.10-py3` and clones
`hailo-ai/mmsegmentation` branch `Hailo-1.0` (Apache-2.0, last push 2023-12-27); it exports with
`tools/pytorch2onnx.py` and compiles with `hailomz compile --ckpt fcn.onnx --yaml fcn8_resnet_v1_18.yaml
--calib-path ...`. It also needs the NVIDIA Container Toolkit. `training/fcn_hailo` exists but its
network yaml is no longer in either tag.

Newer zoo tags add bisenetv2, ddrnet_23_slim, pp_liteseg_t/b, pidnet and yolo26*_sem, but only for
DFC 3.34 / HailoRT 4.24 (v2.19+, Hailo-8) or DFC 5.5 / HailoRT 5.5 (v5.5.0, Hailo-10H). Their HEFs
would not load on the rigs as they are. Ultralytics' own Hailo export of YOLO26 semantic models is
validated on DFC 3.33 / HailoRT 4.23, but Ultralytics is AGPL-3.0.

### Time budget for one 9152 x 6944 photo

Tiles at full resolution with no overlap, divided by Hailo's batch-8 FPS. NPU time only.

| Model | Tiles | Hailo-8 | Hailo-10H |
|---|---|---|---|
| unet_mobilenet_v2 (256x256) | 36 x 28 = 1008 | 1.5 s | 1.5 s |
| deeplab_v3_mobilenet_v2_wo_dilation (513x513) | 18 x 14 = 252 | 1.0 s | 0.7 s |
| stdc1 (1024x1920) | 5 x 7 = 35 | 0.6 s | 1.1 s |
| fcn8_resnet_v1_18 (1024x1920) | 5 x 7 = 35 | 0.8 s | 1.0 s |
| segformer_b0_bn (512x1024) | 9 x 14 = 126 | 5.0 s | 5.7 s |

Overlapping tiles to hide seams multiply these by about 1.5 to 2. One photo is 191 MB as RGB, so
moving it over the Pi 5's single PCIe lane takes roughly 0.25 to 0.5 s each way (estimate, not
measured). The 60 s budget is far away on paper; JPEG decoding of the 64 MP photo and tiling on the
Pi's CPU are likely the larger cost. Measure on each rig before choosing (section 8).

### Candidates for a 2-class plant mask (same three for both chips)

Edge ambiguity is a several-percent area error in this project, so output resolution at the leaf
edge matters more than benchmark mIoU.

1. **unet_mobilenet_v2**: decoder upsamples back to the input size with skip connections, so the
   mask is full resolution. Fastest per pixel, one context on both chips, Apache-2.0. Hailo-8 662
   FPS, Hailo-10H 693 FPS. No zoo retraining Docker, but the source is the TensorFlow segmentation
   tutorial and the zoo parses a `.tflite`; a retrained Keras model can be exported the same way,
   or a PyTorch equivalent exported to ONNX. Input size can be raised (512x512 gives 4x fewer tiles
   at about 4x lower FPS). The zoo `.alls` names a layer (`unet_mobilenet_v2/deconv5`) for
   fine-tuning loss; a custom model needs its own layer name there.
2. **stdc1**: best Cityscapes accuracy here (74.6), stride-8 head with bilinear upsampling and
   argmax on the chip, 35 tiles per photo. Retrainable with the `training/fcn` Docker and the
   mmsegmentation STDC config. Hailo-8 58 FPS (1 context), Hailo-10H 20 / 33 FPS (2 contexts).
3. **fcn8_resnet_v1_18**: the only segmentation model with Hailo's own retraining guide, so the
   lowest-risk route from training to HEF. Heavier (142.8 GOPs) and older. Hailo-8 42.6 FPS,
   Hailo-10H 28 / 34 FPS.

Fallback when compute must be minimal: deeplab_v3_mobilenet_v2_wo_dilation (3.21 GOPs, 262 / 361
FPS), but its coarse output stride blurs leaf edges. Not recommended: segformer_b0_bn
(non-commercial licence, transformer layers, slowest).

---

## 6. DFC constraints, calibration and compiling a custom model

What I could confirm without the login-gated DFC User Guide:

- **ONNX opset**: 8 and 11 to 17 (Hailo staff, 2025-10-27). Opsets 9 and 10 are not supported.
  If the model contains an unsupported layer the compiler fails; there is no CPU fallback.
- **Static shapes**, batch 1 in the ONNX (HailoRT does the batching). Simplify with onnx-simplifier
  first (zoo ONNX files are `*-sim.onnx`).
- **Normalization on the chip**: put `normalization([mean], [std])` in the model script (`.alls`)
  so the HEF takes uint8 RGB. Do not also normalize inside the ONNX.
- **Post-processing on the chip**: the zoo cuts the graph at `ArgMax` (stdc1, fcn8) or adds
  bilinear resize and argmax via `device_pre_post_layers`. For two classes an on-chip argmax gives a
  1-channel uint8 output (least PCIe traffic). Keeping a 2-channel output instead keeps a per-pixel
  confidence, which may matter for the uncertainty the app reports.
- **Large intermediate tensors** can fail allocation ("Agent infeasible", Hailo-10H, 2026-05);
  staff advice is a smaller input (416 or 512 px) or cutting the graph with `end_node_names`.
- **Transformer parts** (LayerNormalization, attention) need rewriting into supported operators.
- The `.alls` syntax used by the zoo: `model_optimization_config(calibration, batch_size=8,
  calibset_size=256)`, `model_optimization_flavor(optimization_level=2, compression_level=0)`,
  `post_quantization_optimization(finetune, policy=enabled, dataset_size=..., epochs=...,
  loss_layer_names=[...])`, `pre_quantization_optimization(activation_clipping, layers={*},
  mode=percentile, clipping_values=[0.01, 99.99])`, `allocator_param(timeout=25m)`.

**Calibration images**

- Zoo route: `--calib-path <dir>` of JPEG/PNG files; the zoo applies the yaml's preprocessing.
- DFC API: `runner.optimize(data)`, where `data` is a NumPy array N x H x W x C (float32, raw
  0 to 255 RGB when normalization is in the model script), or a callable returning a
  `tf.data.Dataset` (what the zoo passes). A dict `{input_name: array}` for multi-input models is
  in Hailo's tutorials; confirm in the User Guide.
- How many: the zoo's `OPTIMIZATION.rst` says "it is recommended to run this step on a GPU machine
  with dataset size of at least 1024 images"; Ultralytics also says at least 1,024 diverse images.
  Statistics use only `calibset_size` images (default 64; unet_mobilenet_v2 uses 256); fine-tuning
  at level 2 uses 1024 by a third-party summary (unet_mobilenet_v2's script sets `dataset_size=2048`). Staff warn that a very
  large calibration set brings in outliers; pair it with activation clipping.
- For the rig: about 1024 tiles cut at the processing scale from photos that span trays, growth
  stages, exposure settings and bare soil. Keep them separate from the evaluation tiles.

**Two ways to compile a retrained model**

1. **Model Zoo yaml/alls** (best when the network is a retrained zoo architecture with the same
   layer names, as in Hailo's FCN guide). Copy the zoo yaml, change `network_path`,
   `parser.nodes` (start/end node), `info.input_shape`/`output_shape`, and point `alls_script` at
   an edited `.alls`. Then:

   ```bash
   hailomz compile --ckpt /work/models/plantseg.onnx --yaml /work/hailo/cfg/plantseg.yaml \
       --calib-path /work/data/calib_tiles/ --hw-arch hailo8 --classes 2
   ```

   `hailomz eval` needs one of the zoo's dataset formats, so accuracy checks on our data are done
   separately. The zoo's own docs say its optimize/eval features are for zoo models and point
   custom models to the DFC.
2. **DFC Python API** (any custom network). Calls below are the ones the zoo source uses:

   ```python
   import numpy as np
   from hailo_sdk_client import ClientRunner, InferenceContext

   runner = ClientRunner(hw_arch="hailo8")            # "hailo10h" in the 5.1.0 image
   runner.translate_onnx_model("plantseg.onnx", "plantseg",
                               start_node_names=["input"], end_node_names=["logits"])
   runner.load_model_script(open("plantseg.alls").read())
   calib = np.load("calib_tiles.npy").astype(np.float32)   # N x H x W x 3, 0..255
   runner.optimize(calib)
   runner.save_har("plantseg_quantized.har")
   with runner.infer_context(InferenceContext.SDK_QUANTIZED) as ctx:   # emulator, before the Pi
       q = runner.infer(ctx, holdout_tiles)
   open("plantseg_hailo8.hef", "wb").write(runner.compile())
   ```

   The `hailo` CLI (`hailo parser onnx`, `hailo optimize`, `hailo compiler`, `hailo profiler`)
   does the same steps. Comparing `SDK_FP_OPTIMIZED` with `SDK_QUANTIZED` output on held-out tiles
   measures the quantization loss on this host, before any rig is involved.

Compile the same ONNX twice, once per image, to get one HEF per chip.

---

## 7. Running a HEF on the Pi (from source and package metadata; rigs not touched)

| | Production (Hailo-8) | Development (Hailo-10H) |
|---|---|---|
| apt metapackage (trixie) | `hailo-all` 5.1.1 | `hailo-h10-all` 5.1.1 (cannot be installed with `hailo-all`) |
| Runtime | `hailort` 4.23.0, `hailort-pcie-driver` 4.23.0 | `h10-hailort` 5.1.1, `h10-hailort-pcie-driver` 5.1.1 |
| Python binding | `python3-hailort` 4.23.0-1, Python 3.13 only | `python3-h10-hailort` 5.1.1-1, Python 3.13 only |
| Module | `hailo_platform` | `hailo_platform` |

- A venv on the rig needs `--system-site-packages` to see the apt binding, or the Developer Zone
  wheel built for the venv's Python version.
- The Python API is the same in 4.23.0 and 5.1.1 (compared `pyhailort.py` at both tags): `HEF`,
  `VDevice`, legacy `InferVStreams`, and the newer `VDevice.create_infer_model(hef)` ->
  `InferModel.set_batch_size(n)`, `.input(name).set_format_type(FormatType.UINT8)`,
  `.configure()` -> `ConfiguredInferModel.create_bindings(input_buffers=, output_buffers=)`,
  `.run(bindings, timeout)`, `.run_async(bindings, callback)`, `.wait_for_async_ready(...)`.
  5.1.1 only adds GenAI internals (KV cache, `HailoSession`). One code path can serve both rigs;
  only the HEF differs.
- **Batch**: `set_batch_size(n)` and pass a list of bindings; `run_async` lets the CPU cut the next
  tiles while the NPU works. With `InferVStreams.infer({name: array})` the batch is the first axis.
- **Multiple inputs/outputs**: addressed by name (`input(name)`, `output(name)`). A segmentation
  model has one of each.
- **Formats**: input uint8 (normalization runs on the chip); output uint8 for an argmax mask, or
  FLOAT32 to get dequantized scores on the host.
- A hailo8 HEF does not load on a Hailo-10H and the reverse. HailoRT 5.x supports Hailo-10/15
  only; Hailo-8 stays on 4.x.
- Hailo-8 has no on-board memory: a multi-context HEF reloads contexts over PCIe. The AI HAT+ 2
  (Hailo-10H) has 8 GB on board. All four prebuilt zoo HEFs are single-context on Hailo-8.
- The Pi 5's external PCIe runs Gen 2 x1 unless `dtparam=pciex1_gen=3` is set; check with
  `lspci -vv` (read only) before trusting any FPS figure.
- CLI checks on a rig: `hailortcli fw-control identify`, `hailortcli parse-hef x.hef`,
  `hailortcli benchmark x.hef`, `hailortcli run x.hef --batch-size 8`.
- **Known Hailo-10H issue**: users report inference wedging with HailoRT 5.1.1 on the AI HAT+ 2
  (`HAILO_TIMEOUT`, reboot needed), including Hailo's resnet_v1_50; staff called it "a vDMA issue in
  the driver" on 2026-05-18, unresolved there. One user's unconfirmed guess is a per-frame input
  size threshold around 270 to 330 KB. A 256x256x3 tile is 196 KB; 512x512x3 is 786 KB.

---

## 8. Suggested first measurement (not done; needs the `hardware` label)

The prebuilt HEFs in `hailo/prebuilt/hailo10h/` were compiled by Hailo with DFC 5.1.0 for
HailoRT 5.1.x. On the development rig, `hailortcli benchmark` on each gives the real Pi 5 FPS and
shows whether the vDMA issue appears, before any training. `hailo/prebuilt/hailo8/` is the same
for production, but production is read only: running anything on its Hailo needs Aaron's approval.

---

## 9. Download record

| What | Source | Version / id | Size | sha256 | Licence |
|---|---|---|---|---|---|
| Model Zoo clone, Hailo-8 | `https://github.com/hailo-ai/hailo_model_zoo.git` | tag v2.18, commit dc402c7ae70149c516324ef9ddff32d27609ae06 | 12 MB | git commit | MIT |
| Model Zoo clone, Hailo-10H | same | tag v5.1.0, commit c13e20e18f8d2913549b9061d7ea2b47d1a18a51 | 9.1 MB | git commit | MIT |
| Docker image `ubuntu:22.04` | Docker Hub | digest sha256:f64b2ffc2f10ab8f8505aa56b2664bd846cbb9df87c7e2532e30f7667021c0e6 | about 78 MB | (digest) | Ubuntu (various free licences) |
| Docker image `nvidia/cuda:12.5.1-runtime-ubuntu22.04` | Docker Hub | repo digest sha256:a057e3228e6c1c4ee1b777ecb3540156f62ce19b5e9082167f44d98fd3c2f378 | 1.46 GB compressed, 3.77 GB unpacked | (digest) | NVIDIA Deep Learning Container License |
| apt packages in the `base` stage | NVIDIA CUDA repo (ubuntu2204), Ubuntu jammy | `libcudnn9-cuda-12` 9.10.2.21-1, `cuda-nvcc-12-5` 12.5.82-1, Python 3.10.12 etc. | 737 MB of .deb files | apt signature checks | cuDNN SLA, CUDA EULA, Ubuntu licences |
| Prebuilt HEFs and profiler reports | `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.18.0/hailo8/` and `.../v5.1.0/hailo10h/` | see table below | 72 MB HEF + 67 MB HTML | `hailo/prebuilt/SHA256SUMS` | Model Zoo MIT; model weights Apache-2.0 (all four) |

| HEF | Size (bytes) | sha256 |
|---|---|---|
| hailo8/unet_mobilenet_v2.hef | 10113071 | e204d8541bb54c1cc847555d517c8c3bc968f4359199e6eecf2c754ee125da7f |
| hailo8/stdc1.hef | 11933685 | 0958ada644eadf31a56c0fc6ce79060e6295b4b561b867f3dc05c0be512d396d |
| hailo8/fcn8_resnet_v1_18.hef | 10098375 | 22e66fd5555e89df1703a760449704aa0f7fb547a9f4e201252045b02a3409af |
| hailo8/deeplab_v3_mobilenet_v2_wo_dilation.hef | 4285664 | 0eda8ef8e2454a546cd43d5c2da30fdec8748750d2ecae17b6dadb81d15529f0 |
| hailo10h/unet_mobilenet_v2.hef | 8641224 | 41d4b9e9ed7672dae84264f322edaaf44638fab16a22fb5c50a5c83170d35623 |
| hailo10h/stdc1.hef | 11372744 | af7996f88e519d132ce43a579b9c70f925ed9a8a77cb2059b602b0a71e1238cf |
| hailo10h/fcn8_resnet_v1_18.hef | 13206896 | 7415db0d06e406d6d56b6acdb425ed3cdc85a8183af7e2a072ce046e842f8797 |
| hailo10h/deeplab_v3_mobilenet_v2_wo_dilation.hef | 2498080 | 725a97cb70c04e43b93ff8d543f023e8e5ea21bcc5cc913a3c5c47ffac734b54 |

Metadata read but not kept (each fetched once into the session scratchpad): Model Zoo README,
CHANGELOG, GETTING_STARTED and setup.py at tags v2.16 to v5.5.0 (raw.githubusercontent.com);
HailoRT `hef.cpp` and `pyhailort.py` at v4.23.0 and v5.1.1; GitHub release metadata for HailoRT
v4.23.0, v5.1.0, v5.1.1; `hailo-apps` `config.yaml` and `resources_config.yaml` on `main`;
Raspberry Pi apt `Packages.gz` for bookworm and trixie arm64
(`http://archive.raspberrypi.com/debian/dists/<dist>/main/binary-arm64/Packages.gz`); NVIDIA CUDA
apt index for ubuntu2204 (3.2 MB); the Hailo mmsegmentation fork's config listing (GitHub API).

Wheels from the Developer Zone: DFC 3.33.1 and DFC 5.1.0, downloaded by Aaron on 2026-11-20. Name,
size and sha256 in sections 11 and 12.

---

## 10. What failed, and what is not verified

- **GPU in Docker**: not available until the NVIDIA Container Toolkit is installed (needs sudo).
- **Hailo Developer Zone**: release notes, the compatibility table and the DFC User Guide all
  redirect to a login, so DFC requirements come from the Model Zoo docs and Hailo staff forum
  posts, and the download labels and file names in section 2 are expected, not seen.
- **Model Zoo v2.18 inconsistency**: README badge and GETTING_STARTED say DFC 3.33.0; setup.py and
  CHANGELOG say 3.33.1. Hailo's hailo-apps maps HailoRT 4.23 to zoo v2.18, so 3.33.1 is the
  intended pairing. Both 3.33.0 and 3.33.1 pair with HailoRT 4.23.0.
- **Not run**: any Pi measurement. (The DFC install and a CPU-only parse/optimize/compile were done
  on 2026-11-20: sections 11 and 12.)
- **Base image build**: worked (section 3). The `dfc` stage is untested; the most likely trouble
  spots are the DFC wheel's own pinned dependencies under pip 26.3 (if one fails, add
  `pip<25` to the `pip install --upgrade` line) and the zoo's old pins.
- **CPU-only fallback is not a real alternative**: without the toolkit, optimization runs at
  level 0 only (section 4).

---

## 11. Hailo-8 build (2026-11-20, CPU only)

**Image**: `npec406/hailo-hailo8:dfc-3.33.1`, id `sha256:6d4766550f47cdcdfd921e3fa3a1721a332ba5b4adac7bc1957ef0e60f5de115`,
13,139,654,084 bytes on disk (Docker reports 13.1 GB disk, 4.22 GB content). Built with
`hailo/docker/hailo.sh build hailo8` from the wheel `hailo_dataflow_compiler-3.33.1-py3-none-linux_x86_64.whl`
(512,191,331 bytes, sha256 `7a8f825ba10d6bc895539d7472a5f461a678d05df216f04146f33e5881619f5e`) and the
zoo clone at v2.18. First build 3 min 26 s on top of the cached base (DFC pip install 68 s, layer
export 87 s). Logs: `hailo/smoke-hailo8/build*.log`.

**Versions seen in the container**: `hailo --version` -> Hailo Dataflow Compiler v3.33.1 (HailoRT
not installed, as intended); `import hailo_sdk_client` OK, `__version__` 3.33.1; `hailomz --version`
-> Hailo Model Zoo v2.18.0 (installed editable from `/opt/hailo_model_zoo`); TensorFlow 2.18.0. The zoo
install downgrades Pillow to 9.3.0 (its pin); no pip conflict errors.

**Fixes to both Dockerfiles** (only the last `RUN` of stage `dfc` changed, so cached layers were reused):

1. `hailo ...` failed for the non-root run user with `PermissionError: '/opt/hailo-venv/bin/hailo_autocompletion'`:
   on its first call the CLI copies tab-completion files into the venv. Now `hailo --version` runs
   once as root at build time.
2. Compile crashed with `spdlog::spdlog_ex ... Failed opening file /opt/hailo-venv/etc/hailo/dfc/hailo_sdk.core.log
   for writing: Permission denied` -> `BackendAllocatorException: Compilation failed with unexpected crash`.
   The DFC logs to `$VIRTUAL_ENV/etc/hailo/dfc/`; the Python loggers skip an unwritable file, the
   C++ allocator aborts. Now that folder is emptied and set to mode 1777 at build time.
3. Added apt `lsb-release` and `bsdextrautils`: the DFC's one-time system check (runs on first
   import, writes a marker to `$VIRTUAL_ENV/etc/hailo/`) reported "Unsupported OS - ." and
   "column: command not found" without them. Cosmetic, but the check now reads Ubuntu 22.04.

**Smoke compile** (`hailo/tools/smoke_compile.py`, outputs in `hailo/smoke-hailo8/`):

- Model: `models/env-smoke/Unet_mobilenet_v2/model_op13_sim.onnx` (smp Unet, MobileNetV2 encoder,
  6.63 M params, 2 classes, opset 13, simplified, dynamic batch). Parsed with
  `net_input_shapes={"input": [1, 3, 512, 512]}`, end node `/segmentation_head/segmentation_head.0/Conv`
  (logits 1x2x512x512, no argmax on chip).
- Model script: `normalization([123.675, 116.28, 103.53], [58.395, 57.12, 57.375])` (ImageNet,
  on chip), `optimization_level=0, compression_level=0`, `calibset_size=64`, batch 8.
- Calibration: 64 synthetic images, uniform random 0..255 (seed 0). Proves the toolchain only; says
  nothing about quantized accuracy.

| Step | Wall time | Peak RSS (largest process) |
|---|---|---|
| parse | 2.0 s | 1.8 GB (Python) |
| optimize, level 0, 64 images | 71.0 s (statistics collection 49 s) | 3.9 GB (Python) |
| compile | 101.5 s (allocation 45 s, kernels + HEF 33 s) | 2.7 GB (compiler child) |

Peak RSS is `ru_maxrss` of the step's own process and of its largest child, measured per step in a
fresh container; the two are not summed.

- HEF: `hailo/smoke-hailo8/unet_mbv2_smoke_hailo8.hef`, 7,424,705 bytes, sha256
  `6a5e2a5587def492ac69c42f930dc3a569997066262518a72b17853ff07abf25`. Single context; cluster
  utilization total: control 75.8%, compute 48.8%, memory 37.7%.
- **Compiler's estimate, not a measurement** (`hailo profiler` on the compiled HAR):
  125.24 FPS, 15.21 ms latency, 1 context, at 512x512 input. Report:
  `hailo/smoke-hailo8/unet_mbv2_smoke_profile.html` (and `.csv`). For scale, Hailo lists 662 FPS for
  the zoo's unet_mobilenet_v2 at 256x256 (4x fewer pixels).
- Per 9152x6944 photo at 512x512 without overlap: 18 x 14 = 252 tiles, about 2.0 s of NPU time at
  the compiler's estimate (arithmetic, not measured).
- The DFC printed "no suitable GPU found, falling back to CPU" throughout. Optimization level 0 is
  what was asked; with a GPU the intended level is 2.
- Not done: running the HEF on a Hailo-8 (`hailortcli parse-hef` / `benchmark` on production needs
  Aaron's approval), and emulator inference comparing float and quantized output.

## 12. Hailo-10H build (2026-11-20, CPU only)

**Image**: `npec406/hailo-hailo10h:dfc-5.1.0`, id `sha256:8634b5b33601966d54ca99100a48e8c28af0660adb59e2dfc837b72134eba187`,
13,196,483,526 bytes on disk (13.2 GB disk, 4.23 GB content). Built with
`hailo/docker/hailo.sh build hailo10h` from `hailo_dataflow_compiler-5.1.0-py3-none-linux_x86_64.whl`
(512,108,136 bytes, sha256 `b0d6aca8309f6d90a3729ccb0d3f3fff4ce56d7c8b6888c8f243cdc9874e0695`) and the
zoo clone at v5.1.0. First build 3 min 32 s. Same three Dockerfile fixes as section 11 (applied to
both files). Logs: `hailo/smoke-hailo10h/build*.log`.

**Versions seen**: `hailo --version` -> Hailo Dataflow Compiler v5.1.0; `import hailo_sdk_client`
OK, 5.1.0; `hailomz --version` -> Hailo Model Zoo v5.1.0; TensorFlow 2.18.0.

**Smoke compile**: same ONNX, input shape, model script, calibration and script as section 11,
`hw_arch="hailo10h"`, outputs in `hailo/smoke-hailo10h/`.

| Step | Wall time | Peak RSS (largest process) |
|---|---|---|
| parse | 2.2 s | 1.8 GB (Python) |
| optimize, level 0, 64 images | 70.6 s | 4.3 GB (Python) |
| compile | 933.0 s = 15 min 33 s (multi-context partition search 13 min 52 s, allocation 32 s, kernels 22 s) | 4.6 GB (compiler child) |

- HEF: `hailo/smoke-hailo10h/unet_mbv2_smoke_hailo10h.hef`, 7,038,080 bytes, sha256
  `cfe41b607a3331555ffbc230b2595775c859b2a4a10df7bfb02bcd45b74eaa7a`. **4 contexts** (the
  partitioner started at 3 and settled on 4), where the Hailo-8 build fits in 1.
- **Compiler's estimate**: `hailo profiler` gives Throughput, Latency and bandwidth as N/A for this
  multi-context HEF (it reports 4 contexts and per-layer data only). A figure needs
  `hailortcli benchmark` on the development rig (`hardware` label), or a profiler run with
  `--runtime-data` collected there. Report: `hailo/smoke-hailo10h/unet_mbv2_smoke_profile.html`.
- For comparison, Hailo's own zoo HEF of unet_mobilenet_v2 at 256x256 is 1 context on Hailo-10H
  (section 5). The 4 contexts here come from the 512x512 input and the uncut 2-channel logits;
  a 256x256 or 384x384 input, or `performance_param(compiler_optimization_level=...)`, may change it.
  Not tried.
- The long compile is the partition search, which ran on about 4.5 CPU cores; it is CPU work, so a
  GPU would not shorten it.

### Both chips, side by side (same ONNX, 512x512, level 0, synthetic calibration)

| | Hailo-8 (DFC 3.33.1) | Hailo-10H (DFC 5.1.0) |
|---|---|---|
| parse | 2.0 s | 2.2 s |
| optimize | 71.0 s | 70.6 s |
| compile | 101.5 s | 933.0 s |
| contexts | 1 | 4 |
| HEF size | 7,424,705 B | 7,038,080 B |
| compiler's FPS / latency estimate | 125.24 FPS / 15.21 ms | N/A (multi-context) |

---

## 13. Trial compile A: stage A plant network, both chips (2026-11-21, CPU only)

A dry run to find compiler problems early. The final network will be compiled again. No rig was
touched; the HEFs have not run on a chip. Development check, emulator only.

**Network.** Stage A, half resolution, fold 1 as `stage-A.md` numbers the folds: `analysis/train/runs/s2_f0/model.pt`
(run folders are numbered from 0, so "fold 1" is `s2_f0`). smp 0.6.0 Unet, MobileNetV2 encoder, input
1x3x256x256, one logit. 6.61 M parameters, 6.69 GOPs per tile (profiler).

**Code.** `experiments/round4-segmentation-nn/code/hailo_compile.py` (steps and method in its docstring) and
`run_hailo_trial.sh` (one docker run per step, `--cpus=10 --memory=16g --memory-swap=16g`, work root and code
folder mounted at their host paths, working directory = the run folder so the DFC log files land there).
Outputs: `hailo/trial-A/`.

```bash
source /home/txoof/temp.nobackup/npec-406-nn/env.sh; cd /home/txoof/temp.nobackup/npec-406-nn/hailo/trial-A
C=/home/txoof/temp.nobackup/wt/npec-406-label-sources/experiments/round4-segmentation-nn/code
python $C/hailo_compile.py tiles          # 12 s
python $C/hailo_compile.py export         # 4 s
$C/run_hailo_trial.sh hailo8 0            # parse optimize emulate compile profile
$C/run_hailo_trial.sh hailo10h 0
$C/run_hailo_trial.sh hailo8 1            # and hailo10h 1; hailo8 2 with steps parse optimize emulate
python $C/hailo_compile.py report         # metrics.md, metrics.json
```

**ONNX.** `torch.onnx.export(..., opset_version=13, dynamo=False)`: torch 2.11 defaults to the dynamo
exporter, which needs `onnxscript` (not installed; no downloads allowed), so the legacy TorchScript exporter
was used. Static 1x3x256x256, input `input`, output `logits`, simplified with onnxsim 0.8.1. 129 nodes,
operators Add, Clip, Concat, Constant, Conv, Relu, Resize only. ONNX Runtime 1.32 against torch float32 on 8
real tiles: max |difference| 2.3e-4, mean 5.1e-6 logits, masks identical. End node
`/segmentation_head/segmentation_head.0/Conv`.

**Normalisation.** In the DFC model script, not the ONNX: `normalization([123.675, 116.280, 103.530],
[58.395, 57.120, 57.375])` (train_cv's ImageNet mean and std times 255). The HEF takes uint8 RGB.

**Tiles.** From the stage A half-resolution cache (`cache/s2/mm/*_img.npy`), centre 256 of each 320 patch,
only photos of fold 1's training dates (183 photos). Photos sorted by key and dealt alternately: calibration
256 tiles from 84 photos, check 200 tiles from 81 other photos. Seed 406. List in `tiles.json`. The check set
is thin on plant: 1.0% of its pixels are plant by the float network (130,639 px), on 87 of the 200 tiles.

**Parse.** Both DFCs parsed the ONNX in 1.4 s with no unsupported layer and no warning. Nothing in the
network had to change.

**Optimisation level on the CPU.** Level 0 is not the only CPU option: when the level is set explicitly in
the model script, levels 1 and 2 also run on the CPU (no "Reducing optimization level" message; the
reduction in section 4 happens only when the level is left at its default).

| Level | What the DFC ran | Optimise time (Hailo-8) | Output SNR |
|---|---|---|---|
| 0 | statistics only | 72.5 s | not reported |
| 1 | statistics, bias correction (5 min 10 s), layer noise analysis | 429.6 s | 25.48 dB |
| 2 | statistics, QFT 4 epochs on 256 tiles (11 min 44 s; "dataset didn't have enough data for dataset_size of 1024"), noise analysis | 825.6 s | 24.64 dB |

Peak RSS: level 0 2.8 GB, level 1 6.2 GB, level 2 6.9 GB (Python process).

**8-bit loss** (emulator SDK_QUANTIZED against the torch float32 network, all 13.1 M pixels of the 200 check
tiles; `metrics.md`). SDK_FP_OPTIMIZED equals torch to 3.7e-6 logits on average (masks identical), so the
loss below is quantisation alone.

| Run | Mean abs logit diff | p99 | IoU at 0.5 | Plant area ratio q / float | IoU, tiles with >= 1000 plant px (33): lowest / median |
|---|---|---|---|---|---|
| Hailo-8, level 0 | 0.792 | 4.42 | 0.969 | 0.997 | 0.947 / 0.974 |
| Hailo-10H, level 0 | 0.792 | 4.42 | 0.969 | 0.997 | |
| **Hailo-8, level 1** | **0.342** | 2.21 | **0.985** | 1.010 | 0.972 / 0.989 |
| **Hailo-10H, level 1** | **0.341** | 2.21 | **0.985** | 1.010 | |
| Hailo-8, level 2 (256 tiles) | 0.364 | 2.31 | 0.982 | 1.005 | |

The two chips quantise the same way (differences in the 4th decimal). The lowest single-tile IoU is 0 in every
run: tiles with 2 to 21 plant pixels lost or gained; at level 0 one tile also lost a 264 px plant entirely.
Level 2 with only 256 tiles is no better than level 1; QFT is meant for 1024 or more tiles and a GPU.

**Compile** (default performance settings).

| | Hailo-8 (DFC 3.33.1) | Hailo-10H (DFC 5.1.0) |
|---|---|---|
| compiled level | 0 and 1 | 0 and 1 |
| compile time | 107.8 s (L0), 107.1 s (L1) | 641.8 s (L0), 529.1 s (L1; partition search 8 min) |
| contexts | 1 | **3** |
| HEF, level 1 | `hailo/trial-A/hailo8_L1/plantseg_s2f0_hailo8.hef`, 6,611,876 B, sha256 `77339e39e19f2982310321027ddc94ae2bed552008e2b1b57b079001fc8fff6d` | `hailo/trial-A/hailo10h_L1/plantseg_s2f0_hailo10h.hef`, 6,553,784 B, sha256 `c040605f165d0e21bf1e13ffdf688dde45526b0ff1df74a16e7d507eb15bf4d9` |
| HEF, level 0 | `hailo8_L0/...hailo8.hef`, 6,611,748 B | `hailo10h_L0/...hailo10h.hef`, 6,553,808 B |
| compiler estimate | 147.37 FPS, 13.26 ms latency, cluster utilisation control 60%, compute 34%, memory 30% | N/A (profiler gives no figure for multi-context HEFs) |

Arithmetic, not measured: one half-resolution photo read as in stage A (432 tiles, stride 192) is 432 / 147
= 2.9 s of Hailo-8 time at the compiler's estimate.

**What could change the network design (not blockers).**

- Hailo-8 speed is set by the decoder's last stage at full tile resolution: the slowest layers are the
  3x3 convolutions at 256x256 (conv44, 32 -> 16 channels, 147 FPS; conv45 255 FPS; final 1x1 conv46 268 FPS)
  and the 128x128 depthwise layers. Hailo's zoo unet_mobilenet_v2 (a different decoder, 28.9 GOPs) reaches
  662 FPS on the same chip. A lighter last decoder block, or `performance_param(compiler_optimization_level=max)`,
  might raise it. Not tried; 2.9 s per photo is far inside the budget.
- Hailo-10H needs 3 contexts at 256x256 where Hailo-8 needs 1, and its compile is 5 to 6 times slower.
  Its real speed needs `hailortcli benchmark` on the development rig (`hardware` label).

**What failed and how it was fixed.** Only the dynamo ONNX exporter (missing `onnxscript`; used
`dynamo=False`). No DFC errors. Warnings: level 0 "not recommended for production use"; level 2 dataset
smaller than `dataset_size` 1024.

**For the final compile.** Use level 1 if it stays CPU-only (best figures here), or level 2 with a GPU and at
least 1024 calibration tiles. Score the quantised network on the truth cells, not only against the float
network: a 1.5% IoU loss against float is of the size of the segmentation differences that stage A compares.

## 14. Final compile: stage F network, both chips, and the 8-bit loss on the truth cells (2026-11-21, CPU only)

Development check, emulator only. No rig was touched and no HEF has run on a chip. The full tables are in
`scratch/406-train/stage-G.md` and `stage-G.png`.

**Networks.** The final network is `analysis/train/runs/s2_final_e40/model.pt`, the network that ships. It uses
stage E's settings (stage A's settings for 40 epochs), trained on every training day with the truths as edited
after the purple check. The 5 stage E fold models (`runs/s2_f{0..4}_e40`) were quantised and emulated so that the
8-bit loss could be cross-validated. They were not compiled to HEFs.

**Code.** `experiments/round4-segmentation-nn/code/hailo_final.py` holds the steps and the method in its docstring.
The driver is `analysis/train/run_fg.sh`, which is resumable and runs each step in its own docker run with
`--cpus=12 --memory=20g --memory-swap=20g` and `TMPDIR` inside the work root. While stage F trained, one DFC job ran
at a time; after that, two. Tables come from `final_fg.py stage_g`. The ONNX export, normalisation and model script
are the same as in trial A (section 13), at level 1 with compression level 0.

**Calibration.** 1024 tiles per model, the DFC's suggestion. This count was kept because the CPU time was
acceptable: level 1 optimise took 24 to 34 min on Hailo-8 and 46 to 50 min on Hailo-10H, with two runs in parallel.
Bias correction is most of that time (20.5 min alone on Hailo-8 for 1024 tiles) and needs about 15 GB of scratch
disk, written in the run folder and deleted afterwards. The peak was about 11 GiB of RAM (the process plus its
largest child). The tiles are the centre 256 px of half-resolution training photo patches (`cache/s2/mm`): half
with plant and half without, shared equally over the UTC dates. Each fold model was calibrated only on its own
training dates. The final network was calibrated on all 30 dates (222 photos).

**Final network compile.**

| | Hailo-8 (DFC 3.33.1) | Hailo-10H (DFC 5.1.0) |
|---|---|---|
| result | HEF, no errors | HEF, no errors |
| optimise / compile | 25.8 min / 1.8 min | 46.8 min / 17.0 min (ran beside another optimise) |
| SNR after quantisation | 24.35 dB | 24.45 dB |
| contexts | 1 | 3 |
| compiler estimate | 147.37 FPS, 13.26 ms | N/A (multi-context) |
| HEF | `hailo/final/plantseg_s2_final_e40_hailo8.hef`, 6,171,502 B, sha256 `6c0cedd3...` | `hailo/final/plantseg_s2_final_e40_hailo10h.hef`, 6,083,944 B, sha256 `5c54fe40...` |
| quantised against float, 200 check tiles | mean abs logit 0.576, mask IoU 0.986 | 0.575, 0.986 |

The HEFs are also in `hailo/final/<chip>_L1/` with their HARs, logs and profiler output. They are about 440 KB
smaller than trial A's HEFs of the same architecture; the cause was not checked.

**8-bit loss on the truth cells, cross-validated.** Each of the 42 training cells was scored by its held-out
stage E fold model, read the way the float scores are read: production cells from the whole photo at half
resolution, development cells from the crop, stride 192 with the middle of each tile kept. The emulator handled
whole photos at about 0.2 to 0.33 s per tile, so production was not reduced to crops. Stitching the float tiles with
the same code reproduced stage E's saved masks with 0 differing pixels.

| Rig | Network | Mean IoU | Mean area error (%) |
|---|---|---|---|
| production (17) | float32 | 0.8784 | 9.40 |
| production (17) | Hailo-8 quantised | 0.8790 | 8.81 |
| production (17) | Hailo-10H quantised | 0.8792 | 8.83 |
| development (25) | float32 | 0.9394 | 3.31 |
| development (25) | Hailo-8 quantised | 0.9356 | 4.10 |
| development (25) | Hailo-10H quantised | 0.9355 | 4.10 |

Quantised minus float, Hailo-8, with the standard deviation over folds:

- production: mean IoU +0.0006 (SD 0.0049); mean area error -0.59 points (SD 2.31)
- development: mean IoU -0.0038 (SD 0.0081); mean area error +0.79 points (SD 1.43)

Hailo-10H is the same to the third decimal. Seedlings (10 cells): mean IoU 0.862 float against 0.860 quantised,
area error 10.5% against 10.3%. Quantised masks mark slightly more plant on both rigs. Most of the development loss
comes from fold 4's model on the 2026-11-09 cells (B28 to B30, 4 to 6% more area).

**For the rig.** Real speed and real 8-bit output on the chips still need `hailortcli benchmark` and a run on
development (`hardware` label). The Hailo-10H's 3 contexts make its speed the open question.
