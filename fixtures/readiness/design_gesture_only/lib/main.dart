import 'package:flutter/material.dart';

class Card extends StatelessWidget {
  const Card({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {},
      child: Container(
        color: Colors.blue,
        child: const Icon(Icons.arrow_forward),
      ),
    );
  }
}

void main() {}
