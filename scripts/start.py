import io
import re
import time
import asyncio
import json
from pathlib import Path

import tensorflow as tf
from bs4 import BeautifulSoup, Tag
import numpy as np
from PIL import Image
import aiohttp

BASEURL = "https://selcrs.nsysu.edu.tw/menu1"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ",
}
now = max_page = 0


def parse_valid_code(img: bytes):
    # Load the image
    image = Image.open(io.BytesIO(img))

    # Convert the image to grayscale
    image = image.convert("L")

    # Get the width of the image
    width = image.size[0]

    # Determine the size of each slice
    slice_width = width // 4

    # Create a list to hold the image slices
    slices = []

    # Slice the image and resize each slice
    for i in range(4):
        slice_img = image.crop(
            (i * slice_width, 0, (i + 1) * slice_width, image.size[1])
        )
        slice_img = slice_img.resize((28, 28))
        slices.append(slice_img)

    # Convert the slices to a NumPy array
    slices = np.array([np.array(slice_img) for slice_img in slices])

    background_color = np.argmax(np.bincount(slices.flatten()))
    slices = abs(slices - background_color) > 10
    # Load the model
    model = tf.keras.models.load_model("keras_28x28_gray_output10.h5")

    # Use the model to make predictions
    predictions = model.predict(slices)

    # Get the predicted classes
    predicted_classes: np.ndarray = np.argmax(predictions, axis=1)

    return "".join(map(str, predicted_classes))


async def fetch(s: aiohttp.ClientSession, index: str, code: str):
    async with s.post(
        f"{BASEURL}/dplycourse.asp?page={index}",
        data={
            "HIS": "",
            "IDNO": "",
            "ITEM": "",
            "D0": "1122",
            "DEG_COD": "*",
            "D1": "",
            "D2": "",
            "CLASS_COD": "",
            "SECT_COD": "",
            "TYP": "1",
            "SDG_COD": "",
            "teacher": "",
            "crsname": "",
            "T3": "",
            "WKDAY": "",
            "SECT": "",
            "nowhis": "1",
            "ValidCode": code,
        },
    ) as resp:
        global now
        now += 1
        r = max_page - now
        print(f"{index:03d} / {r:03d}", f"{int((100 / (max_page or 1)) * r):03d}")
        return await resp.text()


async def main():
    global max_page
    tasks = []
    pages = []

    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as s:
        await s.get(
            f"{BASEURL}/qrycourse.asp?HIS=2",
            headers=DEFAULT_HEADERS,
        )

        while True:
            out = await s.get(
                f"{BASEURL}/validcode.asp?epoch={time.time()}",
                headers=DEFAULT_HEADERS,
            )

            img = await out.read()
            with Path("test.png").open("wb") as f:
                f.write(img)

            code = parse_valid_code(img)
            out = await fetch(s, 1, code)
            print(code)
            if "Wrong Validation Code" in out:
                print("Wrong Validation Code")
            else:
                break

        out = await fetch(s, 1, code)
        max_page = int(re.findall(r"Showing page \d+ of (\d+) pages", out)[-1])

        if max_page == 0:
            print("No data")
            return

        tasks.extend(map(lambda i: fetch(s, i, code), range(2, max_page + 1)))
        pages = await asyncio.gather(*tasks)

    pages = json.loads(Path("pages.json").read_text())
    result = []
    for page in pages:
        html = BeautifulSoup(str(page), "html.parser")
        data = html.select("table > tr[bgcolor]")
        for d in data:
            tags: str = []
            for line_break in d.find_all("br"):
                line_break: Tag
                line_break.replace_with("\n")
            for tag in d.select_one("td:nth-child(25) font") or []:
                tag: Tag
                tags.append(tag.text)
                tag.extract()

            original_data = list(map(lambda x: x.text.strip(), d))
            (
                Change,
                ChangeDescription,
                MultipleCompulsory,
                Department,
                Number,
                Grade,
                Class,
                Name,
                Credit,
                YearSemester,
                CompulsoryElective,
                Restrict,
                Select,
                Selected,
                Remaining,
                Teacher,
                Room,
            ) = original_data[:17]
            ClassTime = original_data[17:24]
            Description = original_data[24]

            result.append(
                {
                    "Url": d.select_one("td:nth-child(8) > small > a").attrs["href"],
                    "Change": Change,
                    "ChangeDescription": ChangeDescription,
                    "MultipleCompulsory": MultipleCompulsory,
                    "Department": Department,
                    "Number": Number,
                    "Grade": Grade,
                    "Class": Class,
                    "Name": Name,
                    "Credit": Credit,
                    "YearSemester": YearSemester,
                    "CompulsoryElective": CompulsoryElective,
                    "Restrict": Restrict,
                    "Select": Select,
                    "Selected": Selected,
                    "Remaining": Remaining,
                    "Teacher": Teacher,
                    "Room": Room,
                    "ClassTime": ClassTime,
                    "Description": Description,
                    "tags": tags,
                }
            )

    Path("test.json").write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )


# # 異動
# Change: str
# # 異動-說明
# Description: str
# # 多門必修
# MultipleCompulsory: str
# # 系所別
# Department: str
# # 課號
# Number: str
# # 年級
# Grade: str
# # 班別
# Class: str
# # 科目名稱
# Name: str

# # 課目大綱
# Url: str

# # 學分
# Credit: str
# # 學年度
# YearSemester: str
# # 必選修
# CompulsoryElective: str
# # 限修
# Restrict: str
# # 點選
# Select: str
# # 選上
# Selected: str
# # 餘額
# Remaining: str
# # 授課教師
# Teacher: str
# # 教室
# Room: str

if __name__ == "__main__":
    asyncio.run(main())
