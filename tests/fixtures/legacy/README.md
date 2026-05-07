# Legacy fixtures (quarantined)

This directory holds fixtures that historically drove the 0.1.0 rules engine
path but do not faithfully represent the cases they purport to model. They
are retained for traceability and as regression inputs for the architectural
fix in Phase A; they are NOT loaded by the Phase A integration tests.

## synthetic_venkateshulu_wp13296_2022

Phase A precursor for WP 13296/2022 (Sri V. Venkateshulu vs The Secretary,
Karnataka High Court, 17 April 2026). The `paragraphs.json` contains
synthetic placeholder text that includes phrases ("within four weeks",
"within sixty days", "within six months") and entities (KIADB, the
Karnataka Industrial Areas Development Act 1966) that are NOT present in
the real judgment. The real judgment is a pure dismissal under the MMDR
Act with no operative directives and no KIADB anywhere.

The 0.1.0 pipeline ran faithfully against this synthetic input and produced
four "active obligation" cards. The cards were structurally consistent with
the synthetic text but wrong against reality. The Phase A schema's
grounding validators reject any directive whose actor is not in the real
respondent list and any plan whose target_role_id is not a valid
respondent FK; the four phantom cards are therefore unconstructible under
the new schema. See `tests/test_phantom_cards_unconstructible.py`.

The integration test that loaded this fixture is at
`tests/integration/test_apvc_pipeline.py` and is now marked
`@pytest.mark.skip` per Phase A acceptance #6. Phase B will retire this
fixture entirely once the real-PDF segmentation pipeline lands.
