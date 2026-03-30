# CUBE Registry Contributor Agreement

> **Note to maintainers:** This document is a placeholder. It must be reviewed and finalized
> by legal counsel (AI Alliance) before the registry goes public. The key clause is captured
> below as a starting point for legal review.

---

## Agreement

By submitting an entry to the CUBE Registry (opening a pull request that adds or modifies a
file in `entries/`), you ("Submitter") agree to the following terms:

### 1. License accuracy

You attest, to the best of your knowledge, that the license information in your entry — including
`legal.wrapper_license`, `legal.benchmark_license.reported`, and `legal.notices` — is accurate
and complete. You understand that this information is displayed publicly in the CUBE Registry and
may be relied upon by third parties when making decisions about benchmark usage.

**You accept personal responsibility for material misrepresentation of license terms.** The AI
Alliance, the CUBE project, and other registry contributors bear no liability for inaccurate
license declarations made in your entry.

### 2. Right to submit

You attest that you have the right to publish the cube wrapper package referenced in your entry
under the declared `legal.wrapper_license`. If the wrapper code incorporates third-party
components, you have verified compatibility with those components' licenses.

### 3. No endorsement

Inclusion of your entry in the CUBE Registry does not constitute endorsement by the AI Alliance
of your benchmark, package, or any claims made about it.

### 4. Registry policies

You agree to comply with the CUBE Registry submission policies, including ownership rules
enforced by `OWNERS.yaml` and the requirement to maintain a valid, installable PyPI package at
the declared version.

### 5. Updates

You are responsible for keeping your entry accurate. In particular, you should update your
entry if the benchmark license changes, if the package is removed from PyPI, or if the
resources declared in the entry become unavailable.

---

*This agreement follows the model established by PyPI (Python Package Index) and npm, where
package publishers attest to rights and accuracy without the registry performing independent
verification. Reference: [PyPI Terms of Service](https://pypi.org/policy/terms-of-use/),
[npm Terms of Use](https://docs.npmjs.com/policies/terms).*

---

**[PENDING LEGAL REVIEW]** — Do not use this document in production until reviewed by AI
Alliance legal counsel.
