vidhub-control
==============

|build_badge| |coveralls_badge|

.. |build_badge| image:: https://img.shields.io/github/workflow/status/nocarryr/vidhub-control/CI%20Test
    :alt: Build Status
.. |coveralls_badge| image:: https://img.shields.io/coveralls/github/nocarryr/vidhub-control
    :alt: Coveralls


Interface with Videohub SDI Matrix Switchers and SmartView Monitors by
`Blackmagic Design <https://www.blackmagicdesign.com>`_.

The primary purpose is for use as a library in other applications, but a GUI
application is included (requires installation of the `Kivy framework <#install-kivy>`_

Since neither the devices nor the software for them support presets or macros,
a need arose for instantaneous multiple routing changes.  This, as well as
setting the names for inputs and outputs within a single application can be
accomplished using this project.

Links
-----

.. list-table::
    :widths: auto

    * - Releases
      - https://pypi.org/project/vidhub-control/
    * - Source code
      - https://github.com/nocarryr/vidhub-control
    * - Documentation
      - https://nocarryr.github.io/vidhub-control/


Dependencies
------------

This project relies heavily on `asyncio` and other features available in
**Python v3.5** or later.

Core
  * `python-dispatch <https://pypi.org/project/python-dispatch>`_
  * `json-object-factory <https://pypi.org/project/json-object-factory>`_
  * `zeroconf <https://pypi.org/project/zeroconf>`_
  * `python-osc <https://pypi.org/project/python-osc>`_
  * `pid <https://pypi.org/project/pid>`_

User interface (optional)
  * `Kivy <http://kivy.org>`_


Installation
------------

Download
^^^^^^^^

.. highlight:: bash

For basic installation, clone or download the source code::

    git clone https://github.com/nocarryr/vidhub-control
    cd vidhub-control


Create virtual environment
^^^^^^^^^^^^^^^^^^^^^^^^^^

*(optional, but recommended)*

Linux/MacOS
"""""""""""

::

    virtualenv --python=python3 venv
    source venv/bin/activate


Windows
"""""""

::

    virtualenv --python=python3 venv
    venv/Scripts/activate

Install vidhub-control
^^^^^^^^^^^^^^^^^^^^^^

::

    python setup.py install


Install Kivy
^^^^^^^^^^^^

*(optional)*

Ensure all dependencies are met for your platform. Instructions can be found
on the `kivy download page <https://kivy.org/#download>`_


Linux (Ubuntu)
""""""""""""""

Follow the instructions for `Installation in a Virtual Environment <https://kivy.org/docs/installation/installation-linux.html#installation-in-a-virtual-environment>`_


Windows
"""""""

::

    pip install docutils pygments pypiwin32 kivy.deps.sdl2 kivy.deps.glew
    pip install kivy.deps.sdl2
    pip install kivy

MacOS
"""""

Follow the instructions for `homebrew <https://kivy.org/docs/installation/installation-osx.html#using-homebrew-with-pip>`_
or `MacPorts <https://kivy.org/docs/installation/installation-osx.html#using-macports-with-pip>`_.


Usage
-----

To launch the user interface (Kivy required):

::

    vidhubcontrol-ui


Note for Windows
^^^^^^^^^^^^^^^^

The `vidhubcontrol-ui` script may not work. If this is the case, it can be
launched by::

    python vidhubcontrol/kivyui/main.py
