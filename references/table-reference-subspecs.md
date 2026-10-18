# 表格与参考文献通用子规格 v1

本文件规定提取问题、字段与验收职责，不提供学校预设，也不表示生成后端已经实现。机器约束在 domain_subspecs.py，主 validate.py 已接入。保持契约 1.0.0 外层格式；新增属性兼容旧实例，新的细化检查适用于这些 structured 属性。历史证据文件保持不变。

## 提取规则

每个属性仍使用 rules 的 target、decision、value、evidence_ids、check_ids、rationale。确定值须来自明确说明、样例、结构或裁决；未知用 unresolved，不用随意的默认值补齐。没有要求不等于允许忽略，更不等于自动设置三线表。覆盖清单应区分已确认、未规定、未读完和有冲突，后两者应保留阻断 issue。

模板说明与稿件内容分开：模板决定格式，稿件提供表格数据及文献信息。保留原始引文、对象位置、样例属性及其来源。文字说明自己的字号或表格教学示例的外观，不自动变成所描述对象的规则。

## 表格：先拆角色，再逐属性提取

至少区分表格对象、表序、表名、表头、表体、表注、续表标题。多层表头、合并单元格、特定行和特定列独立定位；不得只把整张表标为正文。

| 提取维度 | 统一表达 | 必须判断 |
| --- | --- | --- |
| 对齐 | table.alignment；paragraph.alignment；table.cell.vertical_alignment | 表格整体、单元格水平与垂直对齐分开 |
| 文字方向 | table.cell.text_direction | 横排、竖排与竖向边框不是同一属性 |
| 字体与加粗 | 现有 font.*，对准表头／表体／表注角色与语言 | 中文、英文、数字；某行加粗不等于整表加粗 |
| 行距与缩进 | 现有 paragraph.line_spacing、indent.*、spacing.* | 固定／倍数／最小行距；首行、悬挂、左右缩进；有效格式继承 |
| 线条 | table.borders | 三线／网格／自定义；各条线显隐、样式、pt宽度、六位RGB色 |
| 空间 | table.cell_margins、column_widths；layout.gap_after | 内边距、列宽、表后留白分别记录；未细化的 structured 参数仍不可宣称可执行 |
| 表题 | table.caption_position、caption_of 关系、layout.text_gap | 上／下；表序与表名分离；空格种类及数量 |
| 编号 | numbering.scheme/scope/reset/display；numbering.consistency | 允许方案与最终选择分开；图、表、公式分别连续编号、作用域方案一致，不共用一个计数器 |
| 跨页 | table.continuation；table.repeat_header；table.split_rows | 表头行范围、跨页表题、续字、位置、行拆分和单页装不下的高行处理 |

### 线条结构

table.borders 的 data 必须含 model、lines、auxiliary_lines。lines 含 top、header_bottom、bottom、left、right、inside_horizontal、inside_vertical，每项含 visible；可见线还须含 style、width_pt、color。三线模式前三项可见、后四项隐藏。多层表头允许经证据确认的 auxiliary_lines，每项指定 after_header_row 和 line。边框结构只有基本拓扑检查；最终有效边框仍需解析表格、行、单元格和样式的覆盖。

并不预设线宽或颜色。“三线表且边框1磅”仅在相应模板实例中设置允许线条的宽度；不能给每格都画1磅边框。

### 行选择与续表结构

table.row_selection：selector 为 header、body、first、last 或 indices；只有 indices 可带非空的1起始行号数组。header 的实际行集合须由角色定位确定，不能一律假设第一行。

table.continuation：mode 为 forbid_split、repeat_header 或 caption_each_fragment，另含 repeat_header、caption_pattern、caption_alignment、split_rows。需要每个片段表题时，pattern 必须包含 {number}，并指定对齐且重复表头。这个字段表达要求，不会在 Word 自动生成续表；需分页反馈后端实现，不能用重复表头冒充续表标题。

numbering.consistency：members 引用至少两个实际角色ID；scope、continuous、unique、reset_on_scope_change。各角色分别计数，共享同种作用域。custom 的具体规则须进一步注册扩展，不可仅凭字符串 custom 执行。

验收应检查最终各单元格有效边框、指定行字体/加粗、可编辑表格、数据未丢失、编号连续及引用对应；通过渲染检查表题与表体关系、跨页重复表头、续表标题和留白。当前检查器只检查契约，不完成这些 DOCX 验收。

## 参考文献：著录与正文引用两条链

1. 模板端提取正文引用制式、显示方式、组合规则、排序与链接要求，以及各文献类型的著录范例、字段、标记、标点、作者截断规则、日期和标识符策略。外部标准名称及版本仅在源模板明确指定时记录，不默认某版标准。
2. 稿件端逐条保存原文与定位，识别文献类型、作者、题名、年份、载体、卷期页码、出版地/出版社、DOI/URL、访问日期等实际字段；不同类型使用不同字段集，不强制所有文献都有 DOI。
3. 正文逐个引用建立 source occurrence → reference entry 映射；多篇及区间先展开为稳定ID集合，再按目标格式显示。标号可重排，但内容与映射不可错配。
4. 对缺失必需字段、未知类型、重复文献、没有对应条目的引用、未引用条目、同作者同年消歧分别报告；未经授权不联网补造信息，不把教学范例加入稿件文献。

### citation_style（正文引用）

data 含 system（numeric/author_year/custom）、placement（superscript/inline/footnote/endnote）、label_pattern、multiple_separator、range_policy（expand/compress/preserve）、ordering（appearance/author_year/source/custom）、link_policy（required/optional/none）。这是基础字段集；范围界符、作者截断、同年字母等复杂规则应拆成有类型的扩展，未知不能硬写 custom 后执行。

### bibliography_style（文末著录）

data 含 ordering、unreferenced_policy（allow/reject/review）、missing_field_policy（block/review/omit_if_optional）、types、identifier_policy。

types 每项含唯一 type_id、required_fields、optional_fields、field_order、type_marker（可null）、pattern。必填与可选字段不重叠，必填字段都应出现在排列中；排列不得引用未知字段。pattern 是展示描述，不是动态执行代码，复杂条件仍需有测试的格式化后端。identifier_policy 分别处理 doi、url（preserve/normalize/omit_if_allowed）以及 access_date（required/if_available/not_required）。normalize 不授权修改文献事实；omit_if_allowed 仍需模板或任务依据。

字体、字号、行距、悬挂缩进、对齐继续使用现有独立规则，作用于 reference-entry 或其字段角色，而不是隐藏在一个大字符串里。

验收分为：字段完整性和格式规则；正文—条目映射与编号；事实保持和缺失披露；最终渲染及任务要求的点击跳转。检查形状不能证明作者/DOI真实、标点正确或引用支持研究结论。内容真实性审查需单独的来源核验，不混入格式转换。

## 本次范围

已增加通用表达、结构化字段检查与无学校信息的测试。尚未补完三份模板实例，尚未实现表格或参考文献生成，也没有进行成稿验收。用户举出的详细三线表要求是功能需求示例，不是三个模板共同具有的事实。
