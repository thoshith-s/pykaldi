#!/bin/bash

# Installation script for Kaldi
#
set -e

KALDI_GIT="-b kaldi https://github.com/thoshith-s/pykaldi.git"

KALDI_DIR="/kaldi"

if [ ! -d "$KALDI_DIR" ]; then
  git clone $KALDI_GIT $KALDI_DIR
else
  echo "$KALDI_DIR already exists!"
fi

cd "$KALDI_DIR/tools"

# Prevent kaldi from switching default python version
mkdir -p "python"
touch "python/.use_default_python"

./extras/check_dependencies.sh
./install_mkl.sh

make -j $(nproc)

cd ../src
./configure --shared --mkl-root=/opt/intel/mkl
sed -i "s/\-O1/\-O3/g" kaldi.mk
make clean -j && make depend -j && make -j $(nproc)

echo "Done installing Kaldi."
