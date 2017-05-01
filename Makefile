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
	rm -f article_bundle.pdf article.pdf article.log article.aux *~ RazvodityeKrolikov_small.jpg kolskaya.pdf

.PHONY : git-submodule
git-submodule :
	git submodule init
	git submodule update --recursive

git/configure : | git-submodule
	$(MAKE) -C git configure
	cd git && ./configure

git/git : | git/configure
	$(MAKE) CC=$(CC) CXX=$(CXX) AR=$(AR) -C git

kolskaya.pdf : kolskaya.tex
	pdflatex $<

article.pdf : article.tex RazvodityeKrolikov_small.jpg kolskaya.pdf
	pdflatex article
	pdflatex article

%_small.jpg : %.jpg
	convert $< -define jpeg:extent=63kb $@

%_injected.pdf %.pdf.block_offsets : %.pdf fix_oversize_pdf.py
	python fix_oversize_pdf.py $*.pdf $@

%_bundle.pdf : %_injected.pdf %.pdf.block_offsets git/git update_deflate_headers.py
	./make_polyglot.sh $*_injected.pdf $@
	mv $@ $@.polyglot
	./update_deflate_headers.py $@.polyglot $@ $*.pdf.block_offsets
	rm $@.polyglot
