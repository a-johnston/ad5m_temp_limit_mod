mod_name := temp_mod
mod_version := 0.1.0

control := control-2.2.3

base := mod_files
mod := Adventurer5M-$(mod_name)-$(mod_version)
pro_mod := Adventurer5MPro-$(mod_name)-$(mod_version).tgz
images = $(addprefix $(base)/, start.img end.img)

all: $(mod).tgz

# Not actually gz compressed: busybox tar on the 5M does not detect compression and
# auto_run does not pass -z (similarly, stock firmware blobs don't actually use xz)
$(mod).tgz: $(base)/$(control).tar.xz $(images) $(base)/*
	@tar -cf $@ -C $(base) .
	@cp $@ $(pro_mod)
	@echo "Created $@, $(pro_mod)"

$(base)/$(control).tar.xz: $(control)/*
	@tar --exclude='*_original.hex' -cJf $@ -C $(control) .

$(images): $(base)/%.img: screens/%.png
	@magick -size 800x480 xc:none $< -geometry +0+0 -composite -depth 8 bgra:$@

clean:
	@rm -f $(mod).tgz $(pro_mod) $(base)/$(control).tar.xz $(images) 2> /dev/null
