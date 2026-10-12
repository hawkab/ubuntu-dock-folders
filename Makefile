.NOTPARALLEL: build-desktops package-desktops

.PHONY: build build-plasma build-backdrop build-xfce build-desktops package-desktops package-xfce test-xfce check test test-shell test-plasma release install uninstall preview clean

build:
	/usr/bin/python3 scripts/build.py

build-plasma:
	/usr/bin/python3 scripts/build_plasma.py

build-backdrop:
	/usr/bin/python3 scripts/build_backdrop.py

build-xfce:
	/usr/bin/python3 scripts/build_xfce.py

build-desktops:
	/usr/bin/python3 scripts/build.py --zip-only
	$(MAKE) build-plasma build-xfce
	/usr/bin/python3 scripts/build_backdrop.py --backend wayland --build-only
	/usr/bin/python3 scripts/build_backdrop.py --backend x11 --build-only

package-desktops: build-desktops
	/usr/bin/python3 scripts/package_desktops.py

package-xfce:
	/usr/bin/python3 scripts/build_xfce.py --package

test-xfce: build-xfce
	/usr/bin/python3 scripts/test_xfce.py

test-plasma: build-plasma
	/usr/bin/python3 -m unittest discover -v -s tests -p test_plasma_service.py
	/usr/bin/python3 scripts/test_plasma.py
	/usr/bin/python3 scripts/test_plasma_panel.py --lifecycle
	/usr/bin/python3 scripts/test_plasma_panel.py --interaction
	/usr/bin/python3 scripts/test_plasma_panel.py --ui

check: build
	$(MAKE) test

test:
	node --test tests/*.test.js
	/usr/bin/python3 scripts/test_unit.py

test-shell: build
	/usr/bin/python3 scripts/test_shell.py

release:
	/usr/bin/python3 scripts/release.py --publish

install: build
	/usr/bin/python3 scripts/manage.py install --ubuntu-settings

uninstall:
	/usr/bin/python3 scripts/manage.py uninstall

preview: build
	/usr/bin/python3 scripts/preview.py

clean:
	rm -rf build dist
