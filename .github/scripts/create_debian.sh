version=$1
architecture=$2

sudo apt update && sudo apt install -y libffi-dev python3-dev build-essential ruby
sudo gem install fpm
python3 -m venv myenv
. myenv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements/requirements_dev.txt
deactivate

fpm -s python -t deb \
    --force --architecture "$architecture" \
    --url "https://github.com/analogdevicesinc/pyadi-dt" \
    --version "$version-1" \
    --maintainer "Engineerzone <https://ez.analog.com/sw-interface-tools>" \
    --license "" \
    --no-auto-depends \
    --python-package-name-prefix python3 \
    --after-install .github/scripts/postinstall.sh \
    --description "Device tree management tools for ADI hardware
        Documentation at 
        https://analogdevicesinc.github.io/pyadi-dt/main/" .
