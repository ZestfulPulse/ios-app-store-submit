import 'dart:io';

void main() {
  final file = File('note.txt');
  final stat = file.statSync();
  // Reads the file's creationDate to sort notes by recency.
  print(stat.changed);
}
