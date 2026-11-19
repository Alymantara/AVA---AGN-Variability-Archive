<?php
/**
 * How to cite AVA — shown on about.php#cite (the one place the site gives it; other pages link there).
 */

declare(strict_types=1);

function ava_citation_block(): void
{
    ?>
  <ol class="ava-cite-list">
    <li>
      <strong>The archive.</strong> Hernández Santisteban, J.V., et al., in prep. —
      <span class="text-secondary">the AVA data and pipeline paper.</span>
    </li>
    <li>
      <strong>PyTICS</strong>, the ensemble photometric calibration used for every AVA light curve:
      Vieliute, R., et al., 2025, <em>RAS Techniques and Instruments</em>, rzaf021
      (<a href="https://doi.org/10.1093/rasti/rzaf021">doi:10.1093/rasti/rzaf021</a>;
      code: <a href="https://github.com/Astroberta/PyTICS">github.com/Astroberta/PyTICS</a>).
    </li>
    <li>
      <strong>The target papers.</strong> The publications listed under <em>Data citation</em> on each target's page.
    </li>
  </ol>
  <p class="mb-2">Suggested acknowledgement:</p>
  <div class="ava-cite">This work makes use of data from the AGN Variability Archive (AVA) and of observations from the Las Cumbres Observatory global telescope network.</div>
  <p class="small text-secondary mt-2 mb-0">Released AVA products are distributed under the
    <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a> licence.</p>
<?php
}
