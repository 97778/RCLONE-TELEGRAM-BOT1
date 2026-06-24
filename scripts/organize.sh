#!/usr/bin/env bash
set -uo pipefail

SOURCE="${SOURCE:?SOURCE env var required, e.g. Dropbox33:}"
LIMIT_GB="${LIMIT_GB:-200}"
LIMIT_BYTES=$((LIMIT_GB * 1024 * 1024 * 1024))

RETRY_ARGS=(--tpslimit 4 --retries 3 --low-level-retries 10 --timeout 5m)

# rclone reads RCLONE_CONFIG automatically; build --config if set
CONF_ARGS=()
[ -n "${RCLONE_CONFIG:-}" ] && CONF_ARGS=(--config "$RCLONE_CONFIG")

folder_index=1
folder_used=0
safe=$(echo "$SOURCE" | tr -dc 'A-Za-z0-9')
skipped_log="/data/oversized_files_${safe}.txt"
> "$skipped_log"

extensions="mp4 mkv avi mov wmv flv webm m4v mpg mpeg 3gp 3g2 ts m2ts vob ogv divx f4v rm rmvb asf mxf mp3 wav flac aac m4a ogg wma opus alac aiff aif ape dsf amr mid midi au ac3 dts"

filter_args=(--filter "- ${LIMIT_GB}gb*/**")
for ext in $extensions; do
  filter_args+=(--filter "+ *.$ext")
done
filter_args+=(--filter "- **")

tmp_list=$(mktemp)
cleanup() { rm -f "$tmp_list"; }
trap cleanup EXIT

# Use a literal TAB as the field separator: it cannot appear in a path,
# unlike ';' which is valid in filenames.
TAB=$(printf '\t')
rclone "${CONF_ARGS[@]}" lsf "$SOURCE" -R --files-only \
  --format "sp" --separator "$TAB" "${RETRY_ARGS[@]}" "${filter_args[@]}" > "$tmp_list"

total=$(wc -l < "$tmp_list")
echo "PROG:START;$total"

while IFS="$TAB" read -r size file; do
  [ -z "$size" ] && continue
  [ -z "$file" ] && continue

  if [ "$size" -gt "$LIMIT_BYTES" ]; then
    echo "$file ($size bytes) - exceeds ${LIMIT_GB}GB cap, skipped" >> "$skipped_log"
    echo "PROG:SKIP;$file"
    continue
  fi

  if [ $((folder_used + size)) -gt "$LIMIT_BYTES" ] && [ "$folder_used" -gt 0 ]; then
    folder_index=$((folder_index + 1))
    folder_used=0
  fi

  target_folder="${LIMIT_GB}gb${folder_index}"
  filename=$(basename "$file")
  name="${filename%.*}"
  ext="${filename##*.}"
  if [ "$name" = "$ext" ]; then ext=""; else ext=".$ext"; fi

  dest="${SOURCE}${target_folder}/$filename"
  counter=2
  while rclone "${CONF_ARGS[@]}" lsf "$dest" --tpslimit 4 2>/dev/null | grep -q .; do
    filename="${name}_${counter}${ext}"
    dest="${SOURCE}${target_folder}/$filename"
    counter=$((counter + 1))
  done

  if rclone "${CONF_ARGS[@]}" moveto "${SOURCE}${file}" "$dest" "${RETRY_ARGS[@]}" -v; then
    folder_used=$((folder_used + size))
    echo "PROG:MOVED;$size;$folder_index;$file"
  else
    echo "$file ($size bytes) - move FAILED" >> "$skipped_log"
    echo "PROG:FAIL;$file"
  fi
done < "$tmp_list"

echo "PROG:DONE;$SOURCE"
echo "Done with $SOURCE. Skipped log: $skipped_log"
