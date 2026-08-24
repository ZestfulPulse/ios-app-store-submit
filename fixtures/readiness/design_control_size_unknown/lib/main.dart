import 'package:flutter/material.dart';

class FlexibleButton extends StatelessWidget {
  const FlexibleButton({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {},
      child: const Padding(
        padding: EdgeInsets.all(8),
        child: Icon(Icons.close),
      ),
    );
  }
}

void main() {}
