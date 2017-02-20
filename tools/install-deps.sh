#!/bin/sh
KIVY_WHEEL_GLOB="build/Kivy-*linux_x86_64.whl"
KIVY_BUILD_NEEDED=1

pip install -U pip setuptools wheel
pip install -U Cython==0.23

# Find cached wheel for kivy
for file in $KIVY_WHEEL_GLOB ; do
    if [ -e "$file" ] ; then
        echo "Using cached wheel for kivy: $file"
        pip install "$file"
        KIVY_BUILD_NEEDED=0
    fi
done

# Build kivy wheel if not found so it can be cached
if [ "$KIVY_BUILD_NEEDED" -gt 0 ] ; then
    echo "Building kivy wheel..."
    pip wheel --global-option build_ext -r vidhubcontrol/kivyui/requirements.txt -w build/
    for file in $KIVY_WHEEL_GLOB ; do
        if [ -e "$file" ] ; then
            pip install "$file"
        fi
    done
fi

# Install remaining deps
pip install -r requirements-test.txt
