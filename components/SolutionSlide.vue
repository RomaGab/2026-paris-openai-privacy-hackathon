<template>
  <div class="slide-shell">
    <header class="slide-header">
      <span class="eyebrow mint">02 / THE SOLUTION</span>
      <span class="section-mark">NECESSITY CERTIFICATE</span>
    </header>

    <section class="solution-heading">
      <h1>Every field<br /><span>earns its place.</span></h1>
      <p>
        Minimum viable data plus a replayable certificate for every field-level decision.
      </p>
    </section>

    <main class="solution-stage">
      <section class="payload raw-payload">
        <div class="payload-label"><span>INPUT</span><strong>Raw record</strong></div>
        <pre v-pre><code>{
  <span class="keep">issue_description</span>,
  <span class="keep">product_area</span>,
  <span class="drop">urgency</span>,
  <span class="drop">name</span>, <span class="drop">email</span>, <span class="drop">phone</span>,
  <span class="drop">date_of_birth</span>,
  <span class="drop">address</span>, <span class="drop">account_id</span>
}</code></pre>
        <div class="payload-count">9 fields offered</div>
      </section>

      <section class="test-loop" aria-label="Remove, rerun and measure each field">
        <div class="loop-ring">
          <span class="loop-step step-a">REMOVE</span>
          <span class="loop-step step-b">RERUN</span>
          <span class="loop-step step-c">MEASURE</span>
          <div class="loop-center">Δ<br /><small>decision?</small></div>
        </div>
        <div class="flow-arrow">→</div>
      </section>

      <section class="payload minimal-payload">
        <div class="payload-label"><span>OUTPUT</span><strong>Minimal context</strong></div>
        <pre v-pre><code>{
  <span class="keep">issue_description</span>,
  <span class="keep">product_area</span>
}</code></pre>
        <div class="certificate-seal">
          <span class="seal-check">✓</span>
          <div>
            <strong>NECESSITY CERTIFICATE</strong>
            <small>evidence + enforced allowlist</small>
          </div>
        </div>
        <div class="payload-count">2 fields cross</div>
      </section>
    </main>

    <section class="principles principles-five">
      <div><span>01</span><strong>Declare</strong><p>Purpose + expected output</p></div>
      <div><span>02</span><strong>Test</strong><p>Remove one field per run</p></div>
      <div><span>03</span><strong>Decide</strong><p>Block at zero decision changes</p></div>
      <div><span>04</span><strong>Enforce</strong><p>Send approved facts only</p></div>
      <div><span>05</span><strong>Certify</strong><p>Save model, prompt and payloads</p></div>
    </section>

    <footer class="slide-footer">
      <span class="footer-claim">A smaller payload the team can defend.</span>
      <span>NECESSITY CERTIFICATE</span>
    </footer>
  </div>
</template>
