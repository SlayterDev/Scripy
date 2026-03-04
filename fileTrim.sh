#!/usr/bin/env bash

# Trim file names to a max length of 10 characters

for file in *; do
  if [ ${#file} -gt 10 ]; then
    mv "$file" "${file:0:10}"
  fi
done