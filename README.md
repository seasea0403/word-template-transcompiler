# Word 模板转译器

把研究稿件填入已有 Word 模板，并保留可编辑内容与可追溯的格式依据。

这是面向 Agent 的技能与 Python 工具集合：结合模板中的文字说明、格式示例、样式及页面结构，提取统一规则，在模板副本中写入内容，再检查内容、版式与字段。模板中的字体、边距和段落位置由每次输入决定，代码不按学校名选择预设。

## 工作流程

```text
模板和稿件 → 只读调查 → Agent 解释与规则契约 → 内容映射
          → 在副本写入 → 结构及内容检查 → 渲染与字段验证 → 修复
```

Agent 判断说明的作用范围、示例表达的规范、保留区域和规则冲突；确定性代码负责哈希、定位、属性处理、原生对象和检查。规则不明确时保留问题和证据，不补造作者、日期、文献或研究内容。

## 安装为技能

将此仓库克隆到 Codex 的技能目录。若同名目录已经存在，请先确认版本，避免覆盖已有修改。

Windows PowerShell：

```powershell
git clone https://github.com/seasea0403/word-template-transcompiler.git "$env:USERPROFILE/.codex/skills/word-template-transcompiler"
```

macOS / Linux：

```bash
git clone https://github.com/seasea0403/word-template-transcompiler.git "$HOME/.codex/skills/word-template-transcompiler"
```

在可发现该技能的新对话中使用：

```text
使用 $word-template-transcompiler，根据这份 Word 模板和稿件生成可编辑文档。
先提取格式规则、保留区域和冲突，再写入并验证。保留原稿的数据、图片、公式、脚注和文献事实。
```

技能入口是 [SKILL.md](SKILL.md)，详细命令见 [工作流](references/workflow.md)。

## 运行环境

Python 3.11+。核心依赖见 [requirements.txt](scripts/requirements.txt)，目前测试使用 Python 3.12。Markdown 转换另需 Pandoc，标题分词需 Node.js；渲染器和 Word 不包含在仓库中。

可在独立虚拟环境中运行：

```bash
python -m venv .venv
# 激活 .venv 后：
python -m pip install -r scripts/requirements.txt
python scripts/word_template.py doctor
```

在 Codex 提供的文档运行环境中，优先使用其依赖目录。统一入口也支持子命令前的 `--deps <dependency-dir>`，不会修改全局环境。

## 从新模板开始

```bash
# 只读调查，输出目录必须不存在
python scripts/word_template.py intake --template input/template.docx --out-dir work/template-intake

# 保存完整 Pandoc AST 和受支持对象清单
python scripts/word_template.py parse --manuscript input/content.md --pandoc /path/to/pandoc --output work/manuscript-ir.json

# 检查成稿的 OPC、书签、链接和自定义预期
python scripts/word_template.py check --document output/final.docx --template input/template.docx --expected work/expectations.json --report work/structure-check.json
```

`intake` 不会自动理解所有规范。下一步由 Agent 阅读完整特征和模板页面，填规则、槽位及保护清单，再选择适合的写入后端。新模板的原始文件与格式值属于本次运行，不加入通用预设。

## 能力与边界

- 提取页面、节、段落、样式、表格示例及位置，生成有源哈希的特征与契约。
- 保留封面和布局，支持有保护条件的局部文字写入、多槽题名分行、段落角色及原生目录组件。
- 提供表格、可编辑 OMML 公式、脚注、参考文献和交叉引用的写入组件与检查方法。
- 保留原稿事实；格式转换不能改动表格数据、补造文献或用示例代替稿件内容。

全文后端仍是**受限适配器**：默认双语摘要、三级正文、单编号数字引用及特定期刊条目形式。其他文献类型、无脚注稿件、复杂合并表、跨页续表和更多内容流需要适配。它还不是任意模板的一键转换器。

静态跳转、字段存在、Word 刷新、编辑后编号更新和实际点击是不同验证范围。最终成稿需要渲染并逐页检查；机械通过不等于视觉或语义正确。详见 [写入适配](references/writing.md) 和 [检查与修复](references/verification.md)。

Windows 可选的 `scripts/refresh_word.ps1` 在副本上调用本地 Word，带超时与诊断。打包时新版脚本没有取得成功刷新证据，应按实际回执判断，不能把历史文档验证转作此脚本的证明。

## 测试

```bash
python -m unittest discover -s scripts/engine -p "test_*.py"
python -m unittest discover -s scripts -p test_skill.py
python scripts/engine/test_contract.py
```

初始版本通过 130 项组件测试、5 项入口测试和30项独立契约检查。测试覆盖源文件不变、哈希与定位、规则冲突、脚本字体、网格、目录缩进、引用目标及错误原因；这些合成测试不证明所有真实模板均能转换。

CI 会复跑上述检查，不启动 Word 或渲染器。`package-manifest.json` 记录初始技能包中文件的 SHA-256，后续 Git 提交是代码版本的依据。

## 仓库范围

仓库包含技能说明、规格、实现和合成测试，不包含比赛原始模板、研究稿件、历史成稿、账号凭证或提交轨迹。

当前未指定开源许可证；公开可见不代表已经授予开放源码许可。第三方库遵守各自许可证。
