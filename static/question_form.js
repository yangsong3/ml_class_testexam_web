document.querySelector("#question-builder").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const category = String(form.get("category"));
  const categorySelect = event.currentTarget.elements.category;
  const question = {
    id: String(form.get("id")),
    category,
    category_name: categorySelect.options[categorySelect.selectedIndex].text,
    prompt: String(form.get("prompt")),
    choices: form.getAll("choice").map(String),
    answer: Number(form.get("answer")),
    explanation: String(form.get("explanation")),
  };
  const blob = new Blob([`${JSON.stringify(question, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${question.id}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});
