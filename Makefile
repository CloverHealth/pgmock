# Makefile for packaging and testing pgmock
#
# This Makefile has the following targets:
#
# pyenv - Sets up pyenv and a virtualenv that is automatically used
# deactivate_pyenv - Deactivates the pyenv setup
# dependencies - Installs all dependencies for a project (including mac dependencies)
# setup - Sets up the entire development environment (pyenv and dependencies)
# clean_docs - Clean the documentation folder
# clean - Clean any generated files (including documentation)
# open_docs - Open any docs generated with "make docs"
# docs - Generated sphinx docs
# validate - Run code validation
# test - Run tests
# run - Run any services for local development (databases, CSS compiliation, airflow, etc)
# version - Show the version of the package

OS = $(shell uname -s)

MODULE_NAME=pgmock

ifdef CIRCLECI
TEST_COMMAND=pytest --junitxml=$(TEST_REPORTS)/junit.xml
# Use CircleCIs version
PYTHON_VERSION=
# Dont log pip install output since it can print the private repo url
PIP_INSTALL_CMD=pip install -q
# Do local installs without editable mode because of issues with CircleCI's venv
PIP_LOCAL_INSTALL_CMD=pip install -q .
else
TEST_COMMAND=pytest
DEV_PYTHON_VERSION=3.6.2
PIP_INSTALL_CMD=pip install
PIP_LOCAL_INSTALL_CMD=pip install -e .
endif


# Print usage of main targets when user types "make" or "make help"
help:
	@echo "Please choose one of the following targets: \n"\
	      "    setup: Setup your development environment and install dependencies\n"\
	      "    test: Run tests\n"\
	      "    validate: Validate code and documentation\n"\
	      "    docs: Build Sphinx documentation\n"\
	      "    open_docs: Open built documentation\n"\
	      "\n"\
	      "View the Makefile for more documentation about all of the available commands"
	@exit 2


# Sets up pyenv and the virtualenv that is managed by pyenv
.PHONY: pyenv
pyenv:
ifeq (${OS}, Darwin)
	brew install pyenv pyenv-virtualenv 2> /dev/null || true
# Ensure we remain up to date with pyenv so that new python versions are available for installation
	brew upgrade pyenv pyenv-virtualenv 2> /dev/null || true
endif

# Only make the virtualenv if it doesnt exist
	@[ ! -e ~/.pyenv/versions/${MODULE_NAME} ] && pyenv virtualenv ${DEV_PYTHON_VERSION} ${MODULE_NAME} || :
	pyenv local ${MODULE_NAME}
ifdef DEV_PYTHON_VERSION
# If the Python used for development has been upgraded, remove the virtualenv and recreate it
	@[ `python --version | cut -f2 -d' '` != ${DEV_PYTHON_VERSION} ] && echo "Python has been upgraded since last setup. Recreating virtualenv" && pyenv uninstall -f ${MODULE_NAME} && pyenv virtualenv ${DEV_PYTHON_VERSION} ${MODULE_NAME} || :
endif

	# Install all supported Python versions. There are more recent patch releases
	# for most of these but CircleCI doesn't have them preinstalled. Installing a
	# version of Python that isn't preinstalled slows down the build significantly.
	#
	# If you don't have these installed yet it's going to take a long time, but
	# you'll only need to do it once.
	pyenv install -s 3.7.7
	pyenv install -s 3.6.2
	pyenv install -s 3.5.3

	# Set up the dev env and the environments for Tox
	pyenv local ${MODULE_NAME} 3.7.7 3.6.2 3.5.3 


# Deactivates pyenv and removes it from auto-using the virtualenv
.PHONY: deactivate_pyenv
deactivate_pyenv:
	rm .python-version


# Builds any mac dependencies (brew installs, pre-commit, etc). These will not be executed when on CircleCI
.PHONY: mac_dependencies
mac_dependencies:
ifeq (${OS}, Darwin)
# Install pandoc for converting ipython notebooks to restructured text
	brew install pandoc 2> /dev/null || true
endif


# Builds all dependencies for a project
.PHONY: dependencies
dependencies: mac_dependencies
	${PIP_INSTALL_CMD} -U -r dev_requirements.txt  # Use -U to ensure requirements are upgraded every time
	${PIP_INSTALL_CMD} -r test_requirements.txt
	${PIP_LOCAL_INSTALL_CMD}
	pip check


# Performs the full development environment setup
.PHONY: setup
setup: pyenv dependencies


# Clean the documentation folder
.PHONY: clean_docs
clean_docs:
	cd docs && make clean


# Clean any auto-generated files
.PHONY: clean
clean: clean_docs
	python setup.py clean
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg*/
	rm -rf __pycache__/
	rm -f MANIFEST
	find ${MODULE_NAME} -type f -name '*.pyc' -delete
	rm -rf coverage .coverage .coverage*


# Open the build docs (only works on Mac)
.PHONY: open_docs
open_docs:
	open docs/_build/html/index.html


# Build Sphinx autodocs
.PHONY: docs
docs: clean_docs  # Ensure docs are clean, otherwise weird render errors can result
	jupyter nbconvert Tutorial.ipynb --to rst --output docs/tutorial.rst
	cd docs && make html

# Run code validation
.PHONY: validate
validate:
	flake8 -v ${MODULE_NAME}/
	pylint ${MODULE_NAME}
	make docs  # Ensure docs can be built during validation


# Run tests
.PHONY: test
test:
	coverage run -m ${TEST_COMMAND}
	coverage report


# Run any services for local development. For example, docker databases, CSS compilation watching, etc
.PHONY: run
run:
	@echo "No services need to be running for local development"


# Distribution helpers for determining the version of the package
VERSION=$(shell python setup.py --version | sed 's/\([0-9]*\.[0-9]*\.[0-9]*\).*$$/\1/')

.PHONY: version
version:
	@echo ${VERSION}
