.PHONY: build clean setup

build: setup
	jupyter-book build gallery

setup:
	python code/setup_env.py
	python code/inject_paths.py

clean:
	python code/inject_paths.py --reverse
	jupyter-book clean gallery --all