PYTHON ?= uv run python
ENTRYPOINT ?= main.py
OUTPUT_DIR ?= dist
OUTPUT_NAME ?= ggchat
NUITKA_OPTIONS ?=

ifeq ($(shell uname -s),Darwin)
NUITKA_PLATFORM_OPTIONS := --noinclude-dlls=_sounddevice_data/portaudio-binaries/*.dll
endif

.PHONY: all build clean

all: build

build:
	$(PYTHON) -m nuitka \
		--onefile \
		--assume-yes-for-downloads \
		--output-dir=$(OUTPUT_DIR) \
		--output-filename=$(OUTPUT_NAME) \
		$(NUITKA_PLATFORM_OPTIONS) \
		$(NUITKA_OPTIONS) \
		$(ENTRYPOINT)

clean:
	$(RM) -r $(OUTPUT_DIR)
