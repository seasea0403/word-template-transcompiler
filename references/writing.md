# 写入适配与边界

## 组件

scripts/engine/ 从已运行的工具中提取，模块在同一目录相互导入，不依赖比赛目录；无学校配置。

| 组件 | 能力与边界 |
| --- | --- |
| inspect_docx / feature_extraction | 结构、样式、定位、格式候选与契约组装；语义/条件样式仍需复核 |
| inspect_table_samples | 表/行/格的边框和字体证据，不完整计算所有有效边框 |
| validate / domain_subspecs / schema.json | 数据形状、引用、子规格和能力门控，不证明解释正确 |
| manuscript_ir / write_pipeline | 完整 AST 与非执行预检，识别范围有限 |
| bind_format_review / compile_role_bindings | 语义记录绑定到源特征，样例转段落属性 |
| cover_adapter / text_slot_writer / scoped_slot_writer | 有 guard 的槽位写入和封面保护；复杂图形需专门适配 |
| paragraph_roles / blank_flow / title_layout | 脚本字体、网格、留白和两槽题名 |
| toc_component / finalize_toc | 目录层级、链接和 PDF 页码缓存；缓存只覆盖底部页码和可唯一定位的标题 |
| repair_open_fields | 本写入器三 run TC 字段的隐藏和更新开关，不是任意域警告的通用修复 |
| full_writer | 模板副本与 Pandoc 原生对象混合生成，属于受限适配器 |

## 两种接口

统一提取契约 schema_version=1.0.0，包含 sources、locators、evidence、roles、rules、slots、preservation、relations、checks 等。表达范围大于当前全文后端。validate --for-execution 只能接受真实后端的能力声明，不能编造能力绕过 unresolved。

全文后端另用运行目录中的 contract.json、artifact.md、格式 review、角色 bindings 和封面 bindings。统一契约不能直接传给它。write_pipeline 的 authoring_allowed=false 表示只完成非执行预检，不能翻转此标志冒充完成编译。

旧格式 review 输入形状为 `{rules:[{role,properties,evidence_ids,...}],limitations:[...]}`，用 bind_format_review.py 绑定实际源证据与哈希。角色绑定为 `{source_sha256,roles:[{role,sample_id,evidence_ids,rationale,remove_properties,overrides}]}`，交给 compile_role_bindings.py。它与 feature_extraction 的 annotations.json 是不同接口。

全文配置至少涉及 source_sha256、features、review、role_bindings、cover_bindings，及 sections、toc、abstracts、table、number_separator、references、footnote_numbering、extra_roles、role_refinements。具体读取字段以 full_writer.py 为准；新模板从本次证据编译样例和数值，不复制旧学校段落 ID。封面 actions 以 cover_adapter.py 为准，均应绑定源定位、guard、原文条件和保护范围。

准备好本次配置后可运行：

```text
<python> <skill>/scripts/engine/full_writer.py --manuscript <content.md> --template <source.docx> --output <fresh.docx> --run-dir <prepared-run> --pandoc <pandoc> --node <node>
```

prepared-run 必须有已审阅的 contract.json 和 artifact.md，生成文件与收据使用新路径。先验证封面诊断，再生成正文；源哈希匹配不能替代语义和保护区审核。

## 全文后端限制

- 默认是封面、双语摘要、目录、三级正文与文献；metadata 使用 title_zh/title_en 等约定，题名分词还读取中文关键词。其他内容流须适配，不能补造摘要来迎合代码。
- inventory 只索引 `[1]` 单编号，不支持范围引用、作者年份或完整 Pandoc Cite 关系核验。文献解析只接受特定期刊字段形式，并写 `[J]`；其他类型应扩展或保留原文，不能误套类型。
- 公式输出 OMML，章内编号使用 SEQ，内部引用使用 REF。包中已去除原稿特定公式 ID 分支，改用实际公式映射；复杂嵌套和多行表达仍需回归。
- 图片按原字节导入并缩放；当前主要验证 PNG，其他类型需检查 Content Types。行内大图不能盲用正文倍数行距。
- 表格支持明确边框、表头格式、重复表头和行不拆分。跨页续表、复杂合并和不同线宽仍需扩展并实际验证。
- notes 路径假设稿件有脚注部件；无脚注稿件要适配空集合。模板保留脚注和稿件新增脚注要分别保护。
- 一些章/图/表显示仍为静态；不能声称编辑后所有编号都能更新。现有 REF 目标、SEQ 范围和实际编辑测试分别记录。

超出上述范围可复用读取器、统一规格和底层组件并实现适合的后端；不强制走 full_writer。
