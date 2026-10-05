.PHONY: build check install uninstall preview clean

build:
	/usr/bin/python3 scripts/build.py

check: build
	node --test tests/*.test.js
	/usr/bin/python3 -m unittest discover -v -s tests -p 'test_*.py'

install: build
	/usr/bin/python3 scripts/manage.py install --ubuntu-settings

uninstall:
	/usr/bin/python3 scripts/manage.py uninstall

preview: build
	/usr/bin/python3 scripts/preview.py

clean:
	rm -rf build dist
