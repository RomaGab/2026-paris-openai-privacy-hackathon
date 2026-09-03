<template>
  <div class="slide-shell insights-shell">
    <header class="slide-header">
      <span class="eyebrow blue">02 / THE INSIGHTS · STATION F</span>
      <span class="section-mark">NECESSITY CERTIFICATE</span>
    </header>

    <main class="insights-main">
      <section class="insights-copy">
        <h1>The missing question<br />is <span>necessity.</span></h1>
        <p>PII detection finds personal data. It does not measure task value.</p>
        <strong>AI needs context, not identity.</strong>
      </section>

      <section class="insights-film" aria-label="Founder interview film">
        <SlidevVideo autoplay="once" autoreset="slide" :muted="true" playsinline controls>
          <source src="/storyboard_video.mp4" type="video/mp4" />
        </SlidevVideo>
        <span>FOUNDER INTERVIEW FILM</span>
      </section>
    </main>

    <footer class="slide-footer">
      <span class="footer-claim">What does this task actually need?</span>
      <span>NECESSITY CERTIFICATE</span>
    </footer>
  </div>
</template>