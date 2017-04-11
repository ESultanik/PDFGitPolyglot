ifeq ($(shell uname), Darwin)
CC=clang
CXX=clang++
AR=ar
endif

.PHONY : git-submodule
git-submodule :
	git submodule init
	git submodule update --recursive

git/configure : git-submodule
	make -C git configure
	cd git && ./configure

.PHONY : build-git
build-git : git/configure
	$(MAKE) CC=$(CC) CXX=$(CXX) AR=$(AR) -C git
