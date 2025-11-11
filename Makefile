mod_name := temp_mod
mod_version := 0.1.0

control := control-2.2.3

base := $(mod_name)_$(control)
mod := $(mod_name)-$(mod_version)_$(control)
images = $(addprefix $(base)/, start.img end.img)

all: $(mod).tgz

$(mod).tgz: $(base)/$(control).tar.xz $(images)
	@tar -czf $@ $(base)
	@echo "Created $@"

$(base)/$(control).tar.xz: $(control)/*
	@tar --exclude='*_original.hex' -cJf $@ $(control)/*

$(images): $(base)/%.img: screens/%.png
	@magick -size 800x480 xc:none $< -geometry +0+0 -composite -depth 8 bgra:$@

clean:
	@rm -f $(mod).tgz $(base)/$(control).tar.xz $(images) 2> /dev/null
