---
WIP

Information regarding getting RecFilter v3, (and v2), to use an nVidia GPU.

---

**Credits to @Datahell for working all this out.**

---

## Requirement:

Python 3.7.9 -> 3.9.6 - Has been tested on 3.7.9 and 3.9.5

A nVidia GPU with CUDA.

---

## Installation:

Clone/download the repo and enter `pip install -r requirements` to install the RecFilter/Nudenet dependencies.

Make sure you have the latest nVida GFX drivers for your card installed.

Install the latest version of the CUDA Toolkit available from [nVidia](https://developer.nvidia.com/cuda-downloads)

Install the latest version of the cuDNN libraries, this requires registering for a [nVidia Developer account](https://developer.nvidia.com/), (free).

Go to [cuDNN download](https://developer.nvidia.com/rdp/cudnn-download), you will need to login, agree to the license, then select your download.

**NOTE:** It gives a download for `Windows (x86)` but it's actually `Windows (x64)` libraries.

Install the cuDNN as per the instructions: [cuDNN Installation Guide](https://docs.nvidia.com/deeplearning/cudnn/install-guide/index.html)

If you are running Python 3.8/3.9 on Windows 10 then open a Powershell console and enter the following commands:

```
python -m pip uninstall protobuf
python -m pip install protobuf
```

This will ensure you are using the latest version of `protobuf` which fixes a bug with running slow on Windows 10.

Run the following commands in the console while you have it open:

```
python -m pip uninstall -y onnxruntime
python -m pip install onnxruntime-gpu
python -m pip install tensorflow-gpu
python -m pip install tf2onnx
```

**Conversion of the onnx model**

Download the NudeNet detector checkpoint archive, [NudeNet Detector Checkpoint](https://github.com/notAI-tech/NudeNet/releases/download/v0/detector_v2_default_checkpoint_tf.tar), and extract to a directory.

Find the file `detector_v2_default_checkpoint.onnx` on your system, for Windows this will be `C:\Users\<username>\.NudeNet\detector_v2_default_checkpoint.onnx`.

Rename it to `detector_v2_default_checkpoint.onnx.backup`.

Windows:
```
ren detector_v2_default_checkpoint.onnx detector_v2_default_checkpoint.onnx.backup
```
Linux:
```
mv detector_v2_default_checkpoint.onnx detector_v2_default_checkpoint.onnx.backup
```






# The newest CUDA AND cuDNN need to be installed (the latter one needs a registration on Nvidia's site). As long as the current version of CUDA runs with the newest version of onnxruntime-gpu you are good. If you want to install an older onnxruntime (or older NudeNet) you have to install the specific versions of CUDA and cuDNN that onnxruntime-gpu (same version numbers as onnxruntime) needs: https://onnxruntime.ai/docs/reference/execution-providers/CUDA-ExecutionProvider.html
#nudenet doesn't need tensorflow, but it needs onnxruntime-gpu
python -m pip install nudenet
#don't try try to install onnxruntime and onnxruntime-gpu simultaneously (and remove onnxruntime again). it will break onnxruntime-gpu and will have to be reinstalled.
python -m pip uninstall -y onnxruntime
python -m pip install onnxruntime-gpu
#tf2onnx needs tensorflow or tensorflow-gpu, regardess of the version
python -m pip install tensorflow-gpu
python -m pip install tf2onnx
#rename 
C:\Users\xxxxxx\.NudeNet\detector_v2_default_checkpoint.onnx
#to
detector_v2_default_checkpoint.onnx.backup
#download and extract: 
https://github.com/notAI-tech/NudeNet/releases/download/v0/detector_v2_default_checkpoint_tf.tar
python -m tf2onnx.convert --saved-model C:\Users\xxxxxx\.NudeNet\detector_v2_default_checkpoint_tf --opset 11 --output C:\Users\xxxxxx\.NudeNet\detector_v2_default_checkpoint.onnx