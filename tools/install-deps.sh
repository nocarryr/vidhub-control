#!/bin/sh
KIVY_WHEEL_GLOB="build/Kivy-1.10.1-*linux_x86_64.whl"
KIVY_BUILD_NEEDED=1

pip install -U pip setuptools wheel
pip install -U Cython==0.28.2

# Find cached wheel for kivy
for file in $KIVY_WHEEL_GLOB ; do
    if [ -e "$file" ] ; then
        echo "Found cached wheel for kivy: $file"
        KIVY_BUILD_NEEDED=0
    fi
done

# Build kivy wheel if not found so it can be cached
if [ "$KIVY_BUILD_NEEDED" -gt 0 ] ; then
    echo "Building wheels..."
    pip wheel --build-option build_ext -r vidhubcontrol/kivyui/requirements.txt --wheel-dir=build/
fi

# Install from pre-built wheels
pip install --no-cache-dir --no-index --find-links=build/ kivy
pip install --no-cache-dir --no-index --find-links=build/ -r vidhubcontrol/kivyui/requirements.txt
pip install -U -r requirements-test.txt
