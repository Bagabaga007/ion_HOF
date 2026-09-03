#!/bin/bash
# Gaussian 批量运行脚本 (dpdispatcher Task.command 调用)。
# 遍历工作目录下所有 .gjf, 逐个运行 g16, 生成同名 .log。
# 如需 formchk 可自行取消下方注释。

set -o pipefail

G16_EXE="${G16_EXE:-g16}"
G16_ENV="${G16_ENV:-}"
if [ -n "${G16_ENV}" ]; then
    if [ ! -f "${G16_ENV}" ]; then
        echo "Gaussian environment script not found: ${G16_ENV}" >&2
        exit 2
    fi
    # shellcheck disable=SC1090
    source "${G16_ENV}"
fi
set -u

shopt -s nullglob
inputs=(./*.gjf)
if [ "${#inputs[@]}" -eq 0 ]; then
    echo "No Gaussian .gjf inputs found" >&2
    exit 2
fi

status=0
for gjf in "${inputs[@]}"; do
    full_name="$(basename "$gjf")"
    base_name="${full_name%.*}"
    if ! "${G16_EXE}" "$gjf"; then
        echo "Gaussian failed: ${gjf}" >&2
        status=1
        continue
    fi
    if [ ! -f "${base_name}.log" ] || ! grep -qi "Normal termination of Gaussian" "${base_name}.log"; then
        echo "Gaussian output incomplete: ${base_name}.log" >&2
        status=1
    fi
    # formchk "${base_name}.chk" "${base_name}.fchk"
done
exit "${status}"
