const questionDocuments = document.querySelectorAll("[data-question-document]");

if (questionDocuments.length && window.Quill) {
  const BlockEmbed = window.Quill.import("blots/block/embed");

  class ReadonlyQuestionImageBlot extends BlockEmbed {
    static blotName = "questionImage";
    static tagName = "figure";
    static className = "question-image-embed";

    static create(value) {
      const node = super.create();
      const image = document.createElement("img");
      image.src = value.url;
      image.alt = `문제 참고 이미지 ${Number(value.slot) + 1}`;
      image.loading = "lazy";
      node.dataset.slot = String(value.slot);
      node.append(image);
      return node;
    }

    static value(node) {
      return {
        slot: Number(node.dataset.slot),
        url: node.querySelector("img")?.src || "",
      };
    }
  }

  window.Quill.register(ReadonlyQuestionImageBlot);
  questionDocuments.forEach((container) => {
    const documentData = JSON.parse(container.dataset.document);
    documentData.ops = documentData.ops.map((operation) => {
      const slot = operation.insert?.questionImage;
      if (slot === undefined) {
        return operation;
      }
      return {
        ...operation,
        insert: {
          questionImage: {
            slot,
            url: container.getAttribute(`data-image-${slot}`) || "",
          },
        },
      };
    });
    const fallback = container.querySelector(".question-document-fallback");
    const editor = document.createElement("div");
    container.append(editor);
    const quill = new window.Quill(editor, {
      readOnly: true,
      modules: { toolbar: null },
      formats: [
        "bold", "italic", "underline", "header", "list", "align", "questionImage",
      ],
    });
    quill.setContents(documentData);
    fallback.hidden = true;
  });

  if (window.MathJax?.typesetPromise) {
    window.MathJax.typesetPromise(Array.from(questionDocuments));
  }
}

const choiceDocuments = document.querySelectorAll("[data-choice-document]");

if (choiceDocuments.length && window.Quill) {
  choiceDocuments.forEach((container) => {
    const fallback = container.querySelector(".choice-document-fallback");
    const editor = document.createElement("div");
    container.append(editor);
    try {
      const quill = new window.Quill(editor, {
        readOnly: true,
        modules: { toolbar: null },
        formats: ["bold", "italic", "underline"],
      });
      quill.setContents(JSON.parse(container.dataset.document));
      fallback.hidden = true;
    } catch (error) {
      editor.remove();
    }
  });

  if (window.MathJax?.typesetPromise) {
    window.MathJax.typesetPromise(Array.from(choiceDocuments));
  }
}
