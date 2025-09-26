control := control-2.2.3
mod := temp_mod-1.0.0_$(control)
images = $(addprefix $(mod)/, start.img end.img)

all: $(mod).tgz

$(mod).tgz: $(mod)/$(control).tar.xz $(images)
	@tar -czf $@ $(mod)
	@echo "Created $@"

$(mod)/$(control).tar.xz: $(control)/*
	@tar -cJf $@ $(control)/*

$(images): $(mod)/%.img: screens/%.png
	@magick -size 800x480 xc:none $< -geometry +0+0 -composite -depth 8 bgra:$@

clean:
	@rm -f $(mod).tgz $(mod)/$(control).tar.xz $(images) 2> /dev/null
