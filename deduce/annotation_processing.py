from dataclasses import dataclass

import docdeid
from docdeid.annotate.annotation_processor import MergeAdjacentAnnotations, BaseAnnotationProcessor, OverlapResolver


class DeduceMergeAdjacentAnnotations(MergeAdjacentAnnotations):
    def _tags_match(self, left_tag: str, right_tag: str):

        return (left_tag == right_tag) or {left_tag, right_tag} == {
            "patient",
            "persoon",
        }

    def _adjacent_annotations_replacement(
        self,
        left_annotation: docdeid.Annotation,
        right_annotation: docdeid.Annotation,
        text: str,
    ) -> docdeid.Annotation:

        if left_annotation.tag != right_annotation.tag:
            replacement_tag = "patient"
        else:
            replacement_tag = left_annotation.tag

        return docdeid.Annotation(
            text=text[left_annotation.start_char : right_annotation.end_char],
            start_char=left_annotation.start_char,
            end_char=right_annotation.end_char,
            tag=replacement_tag,
        )


@dataclass(frozen=True)
class _PatientAnnotation(docdeid.Annotation):
    is_patient: bool = False


class PersonAnnotationConverter(BaseAnnotationProcessor):

    def process_annotations(self, annotations: set[docdeid.Annotation], text: str) -> set[docdeid.Annotation]:

        new_annotations = set()

        for annotation in annotations:
            new_annotations.add(
                _PatientAnnotation(
                    text=annotation.text,
                    start_char=annotation.start_char,
                    end_char=annotation.end_char,
                    tag="persoon",
                    is_patient="patient" in annotation.tag,
                )
            )

        new_annotations = OverlapResolver(
            sort_by=["is_patient", "length"],
            sort_by_callbacks={"is_patient": lambda x: -x, "length": lambda x: -x},
        ).process_annotations(new_annotations, text=text)

        return set(
            docdeid.Annotation(
                text=annotation.text,
                start_char=annotation.start_char,
                end_char=annotation.end_char,
                tag="patient" if getattr(annotation, "is_patient", False) else "persoon",
            )
            for annotation in new_annotations
        )
