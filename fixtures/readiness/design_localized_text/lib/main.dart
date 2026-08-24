import 'package:flutter/material.dart';

class Greeting extends StatelessWidget {
  const Greeting({super.key});

  @override
  Widget build(BuildContext context) {
    return Text(AppLocalizations.of(context)!.welcomeMessage);
  }
}

void main() {}
