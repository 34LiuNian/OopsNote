export function optionLabel(index: number): string {
  if (!Number.isInteger(index) || index < 0) throw new RangeError("option index must be a non-negative integer");
  let value = index + 1;
  let label = "";
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + value % 26) + label;
    value = Math.floor(value / 26);
  }
  return label;
}
