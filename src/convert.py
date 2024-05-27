import os, glob
import shutil
from collections import defaultdict
import supervisely as sly
from supervisely.io.fs import (
    file_exists,
    get_file_name,
    get_file_name_with_ext,
    get_file_size,
)
from tqdm import tqdm

import src.settings as s
from dataset_tools.convert import unpack_if_archive


def convert_and_upload_supervisely_project(
    api: sly.Api, workspace_id: int, project_name: str
) -> sly.ProjectInfo:
    # Possible structure for bbox case. Feel free to modify as you needs.

    dataset_path = "/home/alex/DATASETS/IMAGES/ENDONUKE/dataset"
    ds_name = "ds"
    batch_size = 30


    def create_ann(image_path):
        tags = []
        image_np = sly.imaging.image.read(image_path)[:, :, 0]

        image_name = get_file_name(image_path)
        ann_pathes = ann_name_to_data.get(get_file_name(image_name))
        # if ann_path is None:
        #     return sly.Annotation(img_size=(image_np.shape[0], image_np.shape[1]))
        for ann_path in ann_pathes:
            labels = []
            annotator_value = ann_path.split("/")[-2]
            tag = sly.Tag(annotator_meta, value=annotator_value)

            if ann_path.split("/")[-3] == "bulk":
                type_tag = sly.Tag(type_meta, value="bulk")
            else:
                type_tag = sly.Tag(type_meta, value="agreement")
                study_value = ann_path.split("/")[-3]
                study_tag = sly.Tag(study_meta, value=study_value)
                tags.append(study_tag)

            tags.append(type_tag)

            with open(ann_path) as f:
                content = f.read().split("\n")

            for curr_point_str in content:
                if len(curr_point_str) != 0:
                    curr_point = list(map(int, curr_point_str.split(" ")))
                    point = sly.Point(curr_point[1], curr_point[0])
                    label = sly.Label(point, index_to_class[curr_point[2]], tags=[tag])
                    labels.append(label)

        return sly.Annotation(
            img_size=(image_np.shape[0], image_np.shape[1]), labels=labels, img_tags=tags
        )


    obj_class_stroma = sly.ObjClass("stroma", sly.Point)
    obj_class_epithelium = sly.ObjClass("epithelium", sly.Point)
    obj_class_other_nuclei = sly.ObjClass("other nuclei", sly.Point)
    index_to_class = {0: obj_class_stroma, 1: obj_class_epithelium, 2: obj_class_other_nuclei}

    annotator_meta = sly.TagMeta(
        "annotator",
        sly.TagValueType.ONEOF_STRING,
        possible_values=["ptg1", "ptg2", "ptg3", "stud1", "stud2", "stud3", "stud4"],
    )
    study_meta = sly.TagMeta(
        "study", sly.TagValueType.ONEOF_STRING, possible_values=["preliminary", "hidden", "posterior"]
    )
    type_meta = sly.TagMeta(
        "type", sly.TagValueType.ONEOF_STRING, possible_values=["bulk", "agreement"]
    )

    project = api.project.create(workspace_id, project_name, change_name_if_conflict=True)


    meta = sly.ProjectMeta(
        obj_classes=[obj_class_stroma, obj_class_epithelium, obj_class_other_nuclei],
        tag_metas=[annotator_meta, study_meta, type_meta],
    )
    api.project.update_meta(project.id, meta.to_json())

    dataset = api.dataset.create(project.id, ds_name, change_name_if_conflict=True)


    images_path = os.path.join(dataset_path, "images")
    images_names = os.listdir(images_path)
    annotation_path = os.path.join(dataset_path, "labels")

    bulk_anns = glob.glob(annotation_path + "/*/*/*.txt")
    agreement_anns = glob.glob(annotation_path + "/*/*/*/*.txt")

    ann_name_to_data = defaultdict(list)

    for curr_ann_path in bulk_anns:
        ann_name = get_file_name(curr_ann_path)
        ann_name_to_data[ann_name].append(curr_ann_path)

    for curr_ann_path in agreement_anns:
        ann_name = get_file_name(curr_ann_path)
        ann_name_to_data[ann_name].append(curr_ann_path)

    progress = sly.Progress("Create dataset {}".format(ds_name), len(images_names))

    for images_names_batch in sly.batched(images_names, batch_size=batch_size):
        img_pathes_batch = [os.path.join(images_path, image_name) for image_name in images_names_batch]

        anns_batch = [create_ann(image_path) for image_path in img_pathes_batch]

        img_infos = api.image.upload_paths(dataset.id, images_names_batch, img_pathes_batch)
        img_ids = [im_info.id for im_info in img_infos]

        api.annotation.upload_anns(img_ids, anns_batch)

        progress.iters_done_report(len(images_names_batch))

    return project
