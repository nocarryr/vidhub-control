[![Build Status](https://travis-ci.org/nocarryr/vidhub-control.svg?branch=master)](https://travis-ci.org/nocarryr/vidhub-control)[![Coverage Status](https://coveralls.io/repos/github/nocarryr/vidhub-control/badge.svg?branch=master)](https://coveralls.io/github/nocarryr/vidhub-control?branch=master)

# vidhub-control

## Overview

Interface with Videohub SDI Matrix Switchers and SmartView Monitors by
[Blackmagic Design](https://www.blackmagicdesign.com/).

The primary purpose is for use as a library in other applications, but a GUI
application is included (requires installation of the [Kivy framework](#install-kivy))

Since neither the devices nor the software for them support presets or macros,
a need arose for instantaneous multiple routing changes.  This, as well as
setting the names for inputs and outputs within a single application can be
accomplished using this project.

## Dependencies

This project relies heavily on `asyncio` and other features available in
**Python v3.5** or later.

* Core
  * [python-dispatch](https://pypi.org/project/python-dispatch/)
  * [json-object-factory](https://pypi.org/project/json-object-factory/)
  * [zeroconf](https://pypi.org/project/zeroconf/)
  * [python-osc](https://pypi.org/project/python-osc/)
  * [pid](https://pypi.org/project/pid/)
* User interface (optional)
  * [Kivy](http://kivy.org/)

## Installation

### Download

For basic installation, clone or download the source code:
```bash
git clone https://github.com/nocarryr/vidhub-control
cd vidhub-control
```

### Create virtual environment (optional, but recommended)

#### Linux/MacOS
```bash
virtualenv --python=python3 venv
source venv/bin/activate
```

#### Windows
```bash
virtualenv --python=python3 venv
venv/Scripts/activate
```

### Install vidhub-control

```bash
python setup.py install
```

### Install Kivy

*optional*

Ensure all dependencies are met for your platform. Instructions can be found
on the [kivy download page](https://kivy.org/#download)

#### Linux (Ubuntu)

Follow the instructions for ["Installation in a Virtual Environment"](https://kivy.org/docs/installation/installation-linux.html#installation-in-a-virtual-environment).

#### Windows

```bash
pip install docutils pygments pypiwin32 kivy.deps.sdl2 kivy.deps.glew
pip install kivy.deps.sdl2
pip install kivy
```

#### MacOS

Follow the instructions for [homebrew](https://kivy.org/docs/installation/installation-osx.html#using-homebrew-with-pip) or [MacPorts](https://kivy.org/docs/installation/installation-osx.html#using-macports-with-pip).

## Usage

To launch the user interface (Kivy required):

```bash
vidhubcontrol-ui
```

### Note for Windows

The `vidhubcontrol-ui` script may not work. If this is the case, it can be
launched by:
```bash
python vidhubcontrol/kivyui/main.py
```


## Documentation

TODO
