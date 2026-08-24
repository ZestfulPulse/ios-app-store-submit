import 'package:flutter/material.dart';

class TinyButton extends StatelessWidget {
  const TinyButton({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 20,
      height: 20,
      child: GestureDetector(
        onTap: () {},
        child: const Icon(Icons.close),
      ),
    );
  }
}

void main() {}
