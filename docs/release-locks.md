# 发布锁定与部署预检

`delivery/release-manifest.json` 使用统一 schema 1，并把验收拆成两个独立 profile：

- `core`：源码/版本完整性和 H5N7 离线数值复算；
- `dispatch`：dpdispatcher 配置、Gaussian/ORCA 输入模板、随包 runner，以及计算节点后端可见性。

对应的精确约束和实测环境分别位于：

- `delivery/locks/core.json`
- `delivery/locks/dispatch.json`

只读预检不会提交任何科学作业：

```bash
python scripts/release_preflight.py --profile core --json
python scripts/release_preflight.py --profile dispatch --json
```

检查部署专用 machine/resources：

```bash
python scripts/release_preflight.py --profile dispatch \
  --machine /path/to/machine.yaml \
  --resources /path/to/resources.yaml \
  --json
```

Gaussian/ORCA 往往只安装在 dpdispatcher 远端计算节点，因此可执行文件检查必须在
真正运行相应程序的节点显式启用：

```bash
python scripts/release_preflight.py --profile dispatch --backend-check gaussian --json
python scripts/release_preflight.py --profile dispatch --backend-check orca --json
```

任一必需检查失败时退出码为 1。冻结版清单中的 `source_revision.commit`
指向经过测试的源码提交；清单作为独立元数据提交，避免在文件中嵌入自身提交哈希。
