ifeq ($(shell uname), Darwin)
CC=clang
CXX=clang++
AR=ar
endif

.PHONY : all
all : article_bundle.pdf

.PHONY : clean
clean : git-submodule
	$(MAKE) -C git clean
	rm article_bundle.pdf article.pdf article.log article.aux *~

.PHONY : git-submodule
git-submodule :
	git submodule init
	git submodule update --recursive

git/configure : | git-submodule
	$(MAKE) -C git configure
	cd git && ./configure

git/git : | git/configure
	$(MAKE) CC=$(CC) CXX=$(CXX) AR=$(AR) -C git

article.pdf : article.tex
	pdflatex $<
	pdflatex $<
	test `wc -c <$@` -lt 65536 # The resulting PDF must be smaller than a DEFLATE block (0xFFFF bytes)!
	@echo "$@ successfully created"

%_bundle.pdf : %.pdf git/git
	./make_polyglot.sh $*.pdf $@
