# 001. No fine-tuning on chat history

**Context.** The original sketch asked "train on past prompts?"

**Decision.** No. Lessons are distilled into a searchable, editable store instead.

**Consequences.** Every fact has a source, a date, and an edit path. A wrong fact is a state
change, not a retrain. Cost is one Haiku call per session instead of a training run.

**Would reopen it.** A style-only LoRA once the store is stable; never for facts.
