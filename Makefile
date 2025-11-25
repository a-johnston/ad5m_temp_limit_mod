mod_name := temp_mod
mod_version := 0.1.1

base := mod_files
out = out
mod := $(out)/Adventurer5M-$(mod_name)-$(mod_version).tgz
pro_mod := $(out)/Adventurer5MPro-$(mod_name)-$(mod_version).tgz
images = $(addprefix $(base)/screens/, start.img end.img fail.img iap_fail.img)

# Not actually gz compressed: busybox tar on the 5M does not detect compression and
# auto_run does not pass -z (similarly, stock firmware blobs don't actually use xz)
$(mod): $(images) $(base)/flashforge_init.sh
	@mkdir -p $(out)
	@tar -cf $(mod) -C $(base) .
	@cp $(mod) $(pro_mod)
	@echo "Created $@, $(pro_mod)"

$(images): $(base)/screens/%.img: screens/%.png
	@mkdir -p $(base)/screens
	@magick -size 800x480 xc:none $< -geometry +0+0 -composite -depth 8 bgra:$@

clean:
	@rm -rf $(out) $(base)/screens
