.PHONY: build check test release install uninstall preview clean

build:
	/usr/bin/python3 scripts/build.py

check: build
	$(MAKE) test

test:
	node --test tests/*.test.js
	/usr/bin/python3 -m unittest discover -v -s tests -p 'test_*.py'

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
