## RecFilter3 - A SFW filter for videos based on [NudeNet](https://github.com/notAI-tech/NudeNet), it **removes** SFW sections with the aim of leaving just NSFW sections of a video.

Completely rewritten from the original by @Datahell

# **Under Construction**

# **This is an unfinished project, do not complain about things not working - fork it and fix it yourself.**

---

## Explanation:

RecFilter3 does the following operations:
 - Generate sample images at pre-determined intervals for the whole video;
 - Submit the images to the NudeNet classification API;
 - Parse the results for each image based on the wanted search parameters;
 - Generate ffmpeg commands to extract the NSFW sections;
 - Combine these sections into a final video.

---

## Requirements:

Python 3.7.6+ - Has been tested on 3.7.6, 3.9.5, and 3.9.6

ffmpeg/ffprobe - Download compiled binaries and add them to the system path.

---

## Installation:

Download the files to a directory and enter `pip install -r requirements` to install the Python modules.

To enable it to use an NVIDIA GPU with CUDA, please read the CUDA section.

You can also use it as part of the post-processing for CTBRec, (not tested but the theory is sound), eg.

`python RecFilter3.py ${absolutePath} -p ${modelSanitizedName} -s ${siteSanitizedName}`


---

## Usage:

```
Python RecFilter3.py file \
       [-i <VALUE>] \
       [-g <VALUE>] \
       [-d <VALUE>] \
       [-e <VALUE>] \
       [-b <VALUE>] \
       [-f <VALUE>] \
       [-p <NAME> [-s <NAME>]] \
       [-q <VALUE>] \
       [-l <VALUE>] \
       [-k <VALUE>] \
       [-v <VALUE>] \
       [-y <VALUE>] \
       [-1 <VALUE>] \
       [-2 <VALUE>] \
       [-3 <VALUE>] \
       [-4 <VALUE>] \
       [-5 <VALUE>] \
       [-6 <VALUE>]
```
| Parameter        | Description |
|------------------|-------------|
| -i, --interval   | Interval between image samples (default: 5) |
| -g, --gap        | Split segments more than x seconds apart (default: 30) |
| -d, --duration   | Discard segments shorter than x seconds (default: 10) |
| -e, --extension  | Extend start and end of segments by x seconds (default: 3) |
| -b, --beginning  | Skip x seconds of beginning (default: 0) |
| -f, --finish     | Skip x seconds of finish (default: 0) |
| -p, --preset     | Name of the config preset to use, eg. model name |
| -s, --subset     | Subset of preset, eg. site that a model appears on |
| -q, --quick      | Lower needed certainty for matches from 0.6 to 0.5 (default: False) |
| -l, --logs       | Keep the logs after every step (default: False) |
| -k, --keep       | Keep all temporary files (default: False) |
| -v, --verbose    | Output working information (default: False) |
| -y, --overwrite  | Confirm all questions to overwrite (batch process) |
| -1, --images     | Only create image samples |
| -2, --analyse    | Only analyse with NudeNet AI. Requires all_images.txt |
| -3, --match      | Only find matching tags. Requires analysis.txt |
| -4, --timestamps | Only find cut positions. Requires matched_images.txt |
| -5, --split      | Only extract segments at cut markers. Requires cuts.txt |
| -6, --save       | Only connect segements and save final result. Requires segments.txt |

Examples:

`python RecFilter3.py d:\captures\cb_freddo_20210202-181818.mp4`

Uses the default values: -i 5 -g 30 -d 10 -e 3 -b 0 -f 0

`python RecFilter3.py d:\captures\cb_freddo_20210202-181818.mp4 -i 45`

Sample image interval is 45 seconds, default values for everything else.

`python RecFilter3.py d:\captures\cb_freddo_20210202-181818.mp4 -b 420 -f 300`

Skip 420 seconds of video at the start and 300 seconds at the end, default values for everything else.

`python RecFilter3.py d:\captures\cb_freddo_20210202-181818.mp4 -p sexy_legs -s supacams`

Look for the preset `sexy_legs` and the subset `supacams` in the configuration file, the values read will override the defaults.

## Config file

**For the configuration file to be detected it has to have the same basename as the script/executable, (eg. `RecFilter3.json` if the script is named `RecFilter3.py`), and reside in the same directory as the script.**

The configuration file is optional, without it RecFilter3 will use default values for its parameters.

The file is in JSON format and contains presets that define what parameters are used for an analysis.

Example:
```
{
  "presets": [
    {
      "note": "This preset will always be executed at the end to fill missing values",
      "name": "default",
      "subset": "",
      "interval": 5,
      "gap": 30,
      "duration": 10,
      "extension": 3,
      "include": "EXPOSED_BREAST,EXPOSED_BUTTOCKS,EXPOSED_ANUS,EXPOSED_GENITALIA,EXPOSED_BELLY",
      "exclude": "",
      "begin": 0,
      "finish": 0,
      "filesuffix": "_recfilter",
      "videoext": "mp4"
    },
    {
      "note": "This preset will be executed through the inherit in presetwithvalues",
      "name": "iwantmkv",
      "videoext": "mkv"
    },
    {
      "note": "This example preset is the one we call first directly via command line. Usually named after the model or site. Inherit causes it to call another preset.",
      "name": "presetwithtags",
      "inherit": "presetwithvalues",
      "include": "EXPOSED_GENITALIA_F,EXPOSED_ANUS"
    },
    {
      "note": "This example preset has a set of values we like to use more often and it attaches another word to the filename.",
      "name": "presetwithvalues",
      "inherit": "iwantmkv",
      "interval": 2,
      "gap": 30,
      "duration": 0,
      "extension": 30,
      "filesuffix": "_i1g30d0e30"
    }
  ]
}
```

### Preset entries:

**All preset parameters are optional except `name`.**

| Parameter  | Description |
|------------|-------------|
| note       | A description of the preset. |
| name       | Name of the preset, eg. model, site, etc. |
| subset     | An optional subset of the preset, eg. preset is a model name, subset is the site. |
| interval   | Interval in seconds between each generated sample image used for analysis. |
| gap        | Split segments more than x seconds apart. |
| duration   | The minimum duration a segment has to be to be included. |
| extension  | Number of seconds to include before/after selected video segment. |
| include    | Body areas to analyse images for, covered or exposed. (More info below.) |
| exclude    | Body areas to exclude when analysing images.  (More info below.) |
| begin      | Number of seconds to skip at the beginning of the video, eg. in the event of a 'highlights' video being shown. |
| finish     | Number of seconds to skip at the end of the video, eg. in the event of a 'highlights' video being shown. |
| filesuffix | A suffix to add to add to the final output file, eg. to indicate preset used |
| videoext   | You can set the output container of the video, eg. MP4, MKV, etc. Default is MP4 |
| inherit    | Chains another preset so that it's values get included. |

### For the `include` and `exclude` values you can have any of the following with multiple items separated by commas.

The valid body areas to detect on are:
| class name          | Description |
|---------------------|-------------|
| EXPOSED_ANUS        | Exposed Anus; Any gender |
| EXPOSED_ARMPITS     | Exposed Armpits; Any gender |
| COVERED_BELLY       | Provocative, but covered Belly; Any gender |
| EXPOSED_BELLY       | Exposed Belly; Any gender |
| COVERED_BUTTOCKS    | Provocative, but covered Buttocks; Any gender |
| EXPOSED_BUTTOCKS    | Exposed Buttocks; Any gender |
| FACE_F              | Female Face |
| FACE_M              | Male Face |
| COVERED_FEET        | Covered Feet; Any gender |
| EXPOSED_FEET        | Exposed Feet; Any gender |
| COVERED_BREAST_F    | Provocative, but covered Breast; Female |
| EXPOSED_BREAST_F    | Exposed Breast; Female |
| COVERED_GENITALIA_F | Provocative, but covered Genitalia; Female |
| EXPOSED_GENITALIA_F | Exposed Genitalia; Female |
| EXPOSED_BREAST_M    | Exposed Breast; Male |
| EXPOSED_GENITALIA_M | Exposed Genitalia; Male |

The following are gender neutral, ie. they will match Male or Female:
| class name          | Description |
|---------------------|-------------|
| FACE                | Face; Any gender |
| FEET                | Feet; Any gender |
| EXPOSED_BREAST      | Exposed Breast; Any gender |
| EXPOSED_GENITALIA   | Exposed Genitalia; Any gender |

A special entry is available:
| class name          | Description |
|---------------------|-------------|
| NONE                | Having this will cause RecFilter3 to exit, ie. no analysis will be performed thereby keeping the original file. |


## CUDA
---
Information regarding getting RecFilter v3, (and v2), to use an NVIDIA GPU.
---

**Credits to @Datahell for working all this out.**

---

## Requirement:

Python 3.7.6 -> 3.9.6 - Has been tested on 3.7.6 and 3.9.5

A NVIDIA GPU with CUDA.

---

## Installation:

**RecFilter3 and NudeNet:**

Clone/download the repo, extract to a directory, then open a console/terminal within that directory.

Install the dependencies by entering:
```
pip install -r requirements.txt
```
or
```
python -m pip install -r requirements.txt
```

If you are running Python 3.8/3.9 on Windows 10 then open a console and enter the following commands:

```
python -m pip uninstall protobuf
python -m pip install protobuf
```

This will ensure you are using the latest version of `protobuf` which fixes a bug with running slow on Windows 10.

**CUDA Drivers:**

Make sure you have the latest nVida GFX drivers for your card installed.

Install the latest version of the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) available from NVIDIA.

Install the latest version of the cuDNN libraries, this requires registering for a [NVIDIA Developer account](https://developer.nvidia.com/), (free).

Go to [cuDNN download](https://developer.nvidia.com/rdp/cudnn-download), you will need to login, agree to the license, then select your download.

**NOTE:** It gives a download for `Windows (x86)` but it's actually `Windows (x64)` libraries.

Install the cuDNN as per the instructions: [cuDNN Installation Guide](https://docs.nvidia.com/deeplearning/cudnn/install-guide/index.html)

Reboot your computer.

**Additional Python Modules:**

Open a console/terminal:

We need to replace `onnxruntime` with `onnxruntime-gpu` to utilise CUDA:
```
python -m pip uninstall -y onnxruntime
python -m pip install onnxruntime-gpu
```
We need to install the TensorFlow modules to convert the model:
```
python -m pip install tensorflow-gpu
python -m pip install tf2onnx
```

**Conversion of the onnx model**

Download the NudeNet detector checkpoint archive, [NudeNet Detector Checkpoint](https://github.com/notAI-tech/NudeNet/releases/download/v0/detector_v2_default_checkpoint_tf.tar), and extract to a directory.

Find the file `detector_v2_default_checkpoint.onnx` on your system, for Windows this will be:

`C:\Users\<username>\.NudeNet\detector_v2_default_checkpoint.onnx`.

Rename it to `detector_v2_default_checkpoint.onnx.backup`.

Windows:
```
ren detector_v2_default_checkpoint.onnx detector_v2_default_checkpoint.onnx.backup
```
Linux:
```
mv detector_v2_default_checkpoint.onnx detector_v2_default_checkpoint.onnx.backup
```

Convert the checkpoint file:
```
python -m tf2onnx.convert --saved-model <path to extracted archive>\detector_v2_default_checkpoint_tf --opset 11 --output <path to original checkpoint file>\detector_v2_default_checkpoint.onnx
```

This should only take a couple of minutes, (depending on your hardware).
