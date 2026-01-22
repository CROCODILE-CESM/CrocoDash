.PHONY: build clean setup

build: setup
	cd gallery
	jupyter-book build --html
	cd ../
	python code/inject_paths_into_notebooks.py --reverse

setup:
	python code/setup_credentials_and_cesm.py
	python code/inject_paths_into_notebooks.py

clean:
	python code/inject_paths_into_notebooks.py --reverse
	rm -f data_paths_loc.json
	cd gallery
	jupyter-book clean gallery --all