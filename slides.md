---
---
theme: default
title: Necessity Certificate
info: |
  Privacy by design for AI systems.
  Paris OpenAI Privacy Hackathon 2026.
author: Necessity Certificate
aspectRatio: 16/9
canvasWidth: 1440
colorSchema: light
transition: fade
layout: full
class: opening-video
---

<SlidevVideo
  autoplay="once"
  autoreset="slide"
  :muted="true"
  playsinline
  controls
  class="opening-film"
  poster="/storyboard-poster.png"
>
  <source src="/storyboard_video.mp4" type="video/mp4" />
</SlidevVideo>

<!--
[Sources]
- Local product-story video: demo/storyboard_video.mp4
-->

---
layout: full
class: deck-slide problem-slide
---

<ProblemSlide />

<!--
[Sources]
- Google Slides, slide 1: The Problem
- README.md, “Problem”
-->

---
layout: full
class: deck-slide solution-slide
---

<SolutionSlide />

<!--
[Sources]
- Google Slides, slide 3: The Solution
- README.md, “Solution” and “Evidence card”
-->

---
layout: full
class: deck-slide prototype-slide
---

<PrototypeSlide />

<!--
[Sources]
- Google Slides, slide 4: The Prototype
- poc/report.json: 16 tickets, field-retention results, and measured accuracy
- poc/sql_minimize.py: fail-closed view and secure storage transforms
-->
