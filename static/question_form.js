const categoryNames = {
  basics: "머신러닝 기초",
  features: "데이터와 피처",
  numpy: "NumPy",
  pandas: "pandas",
  visualization: "데이터 시각화",
};

document.querySelector("#question-builder").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const category = String(form.get("category"));
  const question = {
    id: String(form.get("id")),
    category,
    category_name: categoryNames[category],
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
