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

%_injected.pdf %.pdf.first_block_bytes : %.pdf fix_oversize_pdf.py
	python fix_oversize_pdf.py $*.pdf $@

%_bundle.pdf : %_injected.pdf %.pdf.first_block_bytes git/git
	./make_polyglot.sh $*_injected.pdf $@.polyglot
	./update_deflate_headers.py $@.polyglot $@ `cat $*.pdf.first_block_bytes`
	rm $@.polyglot
