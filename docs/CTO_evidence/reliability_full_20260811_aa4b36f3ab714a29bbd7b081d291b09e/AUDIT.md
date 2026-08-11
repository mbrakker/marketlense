# CTO audit — not verified

The immutable 20-report cohort did not meet its reliability targets: five reports ended in permanent failure, and the frozen-cohort publication closure did not run. The later, user-authorized 11-report subset is separately recorded in `publication_subset_addendum.json`: six posts were created, five were fail-closed before post creation, and neither authenticated readback nor the zero-write repeat could be performed because the WordPress REST target redirected to `/wp-admin/install.php`.

This bundle is a read-only run-scoped export. Strict exact-head CTO collection is explicitly unavailable because unrelated worktree changes were present when the strict collector ran.
