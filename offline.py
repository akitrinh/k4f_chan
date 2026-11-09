"""Measured CPU INT8 OPUS-MT runtime; local model data, no network calls."""

from contextlib import ExitStack
from pathlib import Path
import sys

from voices import adjust_aligned_pronouns, needs_pronoun_alignment

_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = _ROOT / "models" / "opus"


class OpusTranslator:
    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR, threads: int = 2):
        import ctranslate2
        import sentencepiece

        directory = Path(model_dir)
        # Python opens Unicode Windows paths correctly; the native loaders use
        # narrow file names and can reject an otherwise valid Vietnamese path.
        self._source = sentencepiece.SentencePieceProcessor(
            model_proto=(directory / "source.spm").read_bytes()
        )
        self._target = sentencepiece.SentencePieceProcessor(
            model_proto=(directory / "target.spm").read_bytes()
        )
        # Stream weights instead of copying the entire model into a bytes map.
        # CTranslate2 finishes loading before these temporary handles close.
        with ExitStack() as stack:
            files = {
                name: stack.enter_context((directory / name).open("rb"))
                for name in ("config.json", "model.bin", "shared_vocabulary.json")
            }
            self._translator = ctranslate2.Translator(
                str(directory),
                files=files,
                device="cpu",
                compute_type="int8",
                inter_threads=1,
                intra_threads=threads,
            )

    def translate(self, text: str, speaker_role: str) -> str:
        align_pronouns = needs_pronoun_alignment(text, speaker_role)
        # Native SP 0.2.2 mappings use Unicode character offsets (including
        # supplementary-plane characters), on the original source and decoded
        # hypothesis. Re-encoding the target could change piece segmentation.
        source = self._source.encode(text, return_type="offset_mapping")
        # eng-vie has two target scripts. Select modern Vietnamese on the SOURCE
        # side as required by the upstream card, not as a decoder target prefix.
        # CT2 config has add_source_eos=false: reproduce MarianTokenizer's EOS.
        tokens = [">>vie<<", *source["pieces"], "</s>"]
        result = self._translator.translate_batch(
            [tokens],
            beam_size=2,
            max_decoding_length=192,
            return_attention=align_pronouns,
        )[0]
        hypothesis = result.hypotheses[0]
        retained = [
            index for index, token in enumerate(hypothesis)
            if token not in {"</s>", "<s>", "<pad>"}
        ]
        target = self._target.decode(
            [hypothesis[index] for index in retained],
            return_type="offset_mapping",
        )
        if not align_pronouns:
            return target["text"]
        # CT2 exposes [hypothesis][target piece][source piece]. Filter special
        # target pieces and their rows together, retaining prefix/EOS columns.
        rows = result.attention[0] if result.attention else []
        attention = [rows[index] for index in retained] if len(rows) == len(hypothesis) else []
        return adjust_aligned_pronouns(
            text,
            target["text"],
            [(0, 0), *source["offsets"], (len(text), len(text))],
            target["offsets"],
            attention,
            speaker_role,
        )

    def close(self) -> None:
        if self._translator is not None:
            self._translator.unload_model()
            self._translator = None
