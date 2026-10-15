<?php if ($evidenceAttendanceId !== null && $evidenceAttendanceId > 0): ?>
    <button
        class="evidence-thumbnail-button"
        type="button"
        data-evidence-open
        data-evidence-src="<?= $h($evidenceAction . '&id=' . $evidenceAttendanceId) ?>"
        data-evidence-kind="<?= $h($evidenceKind) ?>"
        data-evidence-person="<?= $h($evidencePerson) ?>"
        data-evidence-code="<?= $h($evidenceCode) ?>"
        data-evidence-time="<?= $h($evidenceTime) ?>"
        aria-label="Mở <?= $h($evidenceKind) ?> của <?= $h($evidencePerson) ?>"
    >
        <img class="evidence-thumbnail" src="<?= $h($evidenceAction . '&id=' . $evidenceAttendanceId) ?>" alt="<?= $h($evidenceKind . ' của ' . $evidencePerson) ?>" loading="lazy" width="72" height="54">
    </button>
<?php else: ?>
    <span class="evidence-empty">--</span>
<?php endif; ?>
