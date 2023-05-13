#!/bin/sh

sh -x -c "$(  head .replit | grep -e "run =" | cut -d = -f 2- | cut -d'"' -f2 )"
