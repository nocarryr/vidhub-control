import os
from setuptools import setup, find_packages

BASE_PATH = os.path.abspath(os.path.dirname(__file__))

def get_deps(filename):
    deps = []
    with open(os.path.join(BASE_PATH, filename), 'r') as f:
        for line in f.read().splitlines():
            if line.startswith('#'):
                continue
            deps.append(line)
    return deps

INSTALL_REQUIRES = get_deps('requirements.txt')
EXTRAS_REQUIRE = {
    'kivy':get_deps('vidhubcontrol/kivyui/requirements.txt'),
}

setup(
    name = "vidhub-control",
    version = "0.0.1",
    author = "Matthew Reid",
    author_email = "matt@nomadic-recording.com",
    description = "Control Smart Videohub Devices",
    packages=find_packages(exclude=['tests*']),
    include_package_data=True,
    install_requires=INSTALL_REQUIRES,
    python_requires='>=3.5',
    entry_points={
        'console_scripts':[
            'vidhubcontrol-web = vidhubcontrol.sofi_ui.main:run_app',
            'vidhubcontrol-server = vidhubcontrol.runserver:main',
        ],
        'gui_scripts':[
            'vidhubcontrol-ui = vidhubcontrol.kivyui.main:main [kivy]',
        ],
    },
    extras_require=EXTRAS_REQUIRE,
    platforms=['any'],
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
    ],
)
